# 相机、麦克风与 IMU

来源：

- <https://huggingface.co/docs/reachy_mini/SDK/media-architecture>
- <https://huggingface.co/docs/reachy_mini/SDK/python-sdk>
- <https://huggingface.co/docs/reachy_mini/platforms/reachy_mini/media_advanced_controls>
- <https://huggingface.co/docs/reachy_mini/SDK/gstreamer-installation>

## Daemon 独占音视频

Wireless 和 Lite 共用 `GstMediaServer`。Daemon 打开相机和声卡，本地客户端和远程客户端走不同后端。SDK 看本机 IPC 是否可达，自动选择：

| `media_backend` | 行为 |
|-----------------|------|
| `default` | 与 daemon 同一台机器用 LOCAL，远程用 WEBRTC |
| `local` | 强制 GStreamer IPC 画面 + GStreamer 音频 |
| `webrtc` | 强制 H.264 + Opus。客户端要装 GStreamer，目前 Linux 完整支持 |
| `no_media` | 让 daemon 放开相机和声卡，自己用 OpenCV、sounddevice 等。退出 `with` 时 daemon 会重新占用 |

本地 IPC 画面被限制在约 10 fps，低于采集帧率，避免机内视觉把 CM4 打满。

浏览器不经过原生客户端：信令在 Hugging Face Space，媒体是与机器人的 WebRTC 直连。机外的 Python 推理服务可以用同一套中继协议的 aiortc 客户端，见文档页 Cloud-Backend Consumer。

直接占硬件：

```python
with ReachyMini(media_backend="no_media") as mini:
    import cv2
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    cap.release()
    mini.goto_target(antennas=[0.3, -0.3], duration=0.5)
```

也可以在已连接对象上调用 `release_media()` / `acquire_media()`，重复调用是安全的。

## 相机

Python：

```python
with ReachyMini(media_backend="default") as mini:
    frame = mini.media.get_frame()  # numpy uint8, (H, W, 3)；排障写明与 OpenCV 兼容的 BGR
```

在机器人上用系统工具看相机（IMX708 广角）：

```bash
rpicam-hello --list
rpicam-still -t 1 -r -o test.jpg --width 4608 --height 2592
scp pollen@reachy-mini.local:/home/pollen/test.jpg .
```

手动对焦示例：`--autofocus-mode manual --lens-position 0` 或 `1000`。Daemon 里对应 GStreamer `libcamerasrc`，可用 `gst-inspect-1.0 libcamerasrc` 看参数。树莓派相机软件说明：<https://www.raspberrypi.com/documentation/computers/camera_software.html>。

对焦不上时，先看镜头是不是被外壳顶住：相机用 4 颗螺丝固定在黑色件上，可把螺丝各松开大约 1/8 圈。人脸跟踪慢，多半是光线；机内应用用 LOCAL 后端延迟最低。

## 麦克风、扬声器、声源方向

4 麦阵列在系统里显示为 `Pollen Robotics Reachy Mini Audio`。默认 AEC。`alsamixer` 里用 F6 选声卡、F5 看输入输出；官方建议除 PCM（输出音量）外都放在 100%。

音量偏低时先把系统更新到 1.2.3 或更新，固件到 2.1.4 或更新。Linux 上把 PCM1 设到 100%，再用 PCM,0 调整体音量。

SDK 音频（输入输出都会被占用，直到 stop）：

```python
with ReachyMini(media_backend="default") as mini:
    mini.media.start_recording()
    mini.media.start_playing()
    samples = mini.media.get_audio_sample()   # (samples, 2) float32, 16 kHz
    mini.media.push_audio_sample(samples)     # (samples, 1 或 2) float32, 16 kHz，非阻塞
    doa, is_speech = mini.media.get_DoA()
    # 0 rad 左侧，π/2 前/后，π 右侧
    mini.media.stop_recording()
    mini.media.stop_playing()
```

Wireless 上 USB 声卡接在 CM4。远程应用不必 SSH，可以走 REST：

```bash
curl http://reachy-mini.local:8000/api/audio/config/parameter/AUDIO_MGR_MIC_GAIN
curl -X POST http://reachy-mini.local:8000/api/audio/config/apply \
  -H 'Content-Type: application/json' \
  -d '{"config":[{"name":"AUDIO_MGR_MIC_GAIN","values":[1.0]}],"verify":true}'
```

同一台机器上的应用也可以 `mini.media.audio.apply_audio_config(...)`。JS 侧是 `robot.applyAudioConfig` / `robot.readAudioParameter`。更底层的 XMOS 参数用仓库里的 `src/reachy_mini/media/audio_control_utils.py`（如 `PP_MIN_NS`、`DOA_VALUE`、`DOA_VALUE_RADIANS`）。参数表见 XMOS XVF 用户指南。

线性阵列：右天线靠近 mic 0，左天线靠近 mic 3。要四路原始麦，需安装仓库 `src/reachy_mini/assets/firmware` 里的 6 通道固件。

在机器人上用 GStreamer 自测：

```bash
gst-launch-1.0 -e alsasrc device="reachymini_audio_src" ! audioconvert ! audioresample ! wavenc ! filesink location="test.wav"
gst-launch-1.0 filesrc location=test.wav ! wavparse ! audioconvert ! alsasink device=reachymini_audio_sink
gst-launch-1.0 audiotestsrc wave="pink-noise" ! audioconvert ! audioresample ! alsasink device="reachymini_audio_sink"
```

若配置报 `No Reachy Mini Audio USB device found!`，说明代码跑错了机器：Wireless 的声卡在机器人上，不在你的笔记本上。同时确认家目录有 `.asoundrc`，`arecord -l` / `aplay -l` 能看到设备。

## 扬声器均衡

头壳会让声音发闷。Daemon 在输出上插了 GStreamer `equalizer-10bands`，默认增益（dB）：

| Hz | 29 | 59 | 119 | 237 | 474 | 947 | 1889 | 3770 | 7523 | 15011 |
|----|----|----|-----|-----|-----|-----|------|------|------|-------|
| dB | 0 | -13.2 | -5.6 | -4.3 | -4.3 | +5.8 | +4.7 | +4.9 | +3.4 | 0 |

覆盖文件：`/home/pollen/.config/reachy_mini/daemon_config.json`

```json
{ "speaker_eq_gains": [0.0, -13.21, -5.55, -4.28, -4.32, 5.80, 4.65, 4.90, 3.41, 0.0] }
```

必须正好 10 个数。全 0 等于关掉均衡。改完重启 daemon。重标定工具在 `src/reachy_mini/tools/speaker_eq_calibration/`。

## IMU（仅 Wireless）

```python
with ReachyMini() as mini:
    imu = mini.imu
    accel = imu["accelerometer"]   # m/s^2, xyz
    gyro = imu["gyroscope"]        # rad/s, xyz
    quat = imu["quaternion"]       # w, x, y, z
    temperature = imu["temperature"]  # °C
```

示例：<https://github.com/pollen-robotics/reachy_mini/tree/main/examples/imu_example.py>
