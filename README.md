# Active Focus Lock System for TIRF and HiLO Microscopy
An open-source, low-cost active focus lock system for fluorescence microscopy, achieving ~8 nm axial stability using back-reflected illumination and PI feedback control.

![FocusLock](https://github.com/user-attachments/assets/52a0cbe7-8793-4c48-9230-8030fc96b974)

## Features

-  Real-time axial stabilization with ~8 nm precision
-  Low-cost implementation using standard webcam
-  Proportional-Integral (PI) feedback control
-  Live monitoring and data logging
-  Automated calibration routine
-  Compatible with Mad City Labs piezo nanopositioners

## System Requirements

### Hardware
- Fluorescence microscope with HiLO or TIRF illumination
- USB webcam (any basic model works)
- Mad City Labs NanoDrive piezoelectric nanopositioner
- Pick-off mirror for beam redirection

### Software
- Windows 7/10/11 (for Mad City Labs DLL)
- Python 3.7+
- Mad City Labs NanoDrive software and DLL

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/focus-lock-system.git
cd focus-lock-system
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure Mad City Labs DLL is installed (default path): C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll

## Quick Start

1. Run the software:
```bash
python focus_lock.py
```

2. **Select a beam-position detection method** (see [Beam Position Detection Methods] below). The contour centroid method is recommended as the default, as it is the most robust across illumination angles and imaging depths.

3. **Calibrate** before first use (and before every acquisition session):
   - Click "Calibrate" button
   - System will move piezo through 10 steps of 60 nm
   - Linear curve will be displayed
   - Only if a linear relationship is detected continue. If there is no linear relationship, adjust acquisition/detection parameters first (digital gain, gamma correction, binarization threshold), and if that doesn't resolve it, adjust optics (add a neutral density filter before the webcam, adjust the HiLO/TIRF illumination angle, verify imaging depth, center the beam on the webcam, or partially close the iris).

4. **Lock focus**:
   - Adjust Kp and Ki parameters (On our system: Kp=-0.01, Ki=-0.001)
   - Click "Lock Focus"
   - Monitor stability in real-time plot
   - If focus lock is not working consider optimizing Kp and Ki to your system.

5. **Monitor stability**:
   - Click "Calculate Std Dev" to measure fluctuations
   - Enable "Save Data" to log position over time

## Usage Guide

### Beam Position Detection Methods

The system supports three alternative methods for estimating the lateral position of the reflected beam on the webcam sensor:

1. **1D Gaussian fitting** – fits a Gaussian profile to a horizontal line profile through the beam center.
2. **2D Gaussian fitting** – fits a Gaussian to the full 2D beam profile.
3. **Contour centroid** – computes the beam position as the center of mass of a contour defined by a binary mask.

All three methods give comparable results under optimal conditions and near the coverslip. However, the **contour centroid method is more robust** at larger distances from the coverslip and across different illumination angles, where the reflected beam deviates from an ideal Gaussian profile and its intensity distribution becomes less reliable. For this reason, contour centroid is the recommended default, especially for HiLO acquisitions at varying depths or low signal intensity.

### Camera / Detection Parameters

To optimize beam detection and calibration linearity, the following acquisition/detection parameters are user-adjustable from the GUI:

- **Digital gain** – amplifies the camera signal; useful for low-intensity conditions (e.g., steep HiLO angles), but excessive gain can introduce noise or saturation.
- **Gamma correction** – adjusts the non-linear response of the recorded intensity; can help linearize the beam profile response.
- **Binarization threshold** – (used only with the contour centroid method) sets the intensity cutoff for generating the binary mask used to compute the contour; affects the size/shape of the detected contour and therefore the precision of the centroid.

Tuning these parameters is typically the first step when troubleshooting a non-linear calibration curve, before resorting to optical adjustments (see Troubleshooting below).


### PI Controller Parameters

- **Kp (Proportional gain)**: Typical value -0.01
  - More negative = stronger immediate response
  - Too high → oscillations
  
- **Ki (Integral gain)**: Typical value -0.001
  - Eliminates steady-state error
  - Too high → instability

### Calibration

The system requires  before each session to establish the relationship between beam displacement and axial position.

** procedure:**
1. Ensure proper illumination and back-reflection
2. Click "Calibrate"
3. Wait ~15 seconds for automated routine
4. Verify linear relationship in  plot
5. Slope is automatically saved

See calibration_guide.md for troubleshooting non-linear calibrations.

### Data Logging

- **Real-time monitoring**: 50-point rolling window
- **CSV export**: Time-stamped position data
- **Stability metrics**: Standard deviation calculation

## How It Works

The system tracks lateral displacement of back-reflected excitation light to measure axial drift:

1. **Image acquisition**: Webcam captures reflected beam at 20 Hz
2. **Signal processing**: 
   - Extract blue channel
   - Gaussian filtering (σ=1 pixel)
   - - Estimate beam position using the selected method: 1D Gaussian fit, 2D Gaussian fit, or contour centroid (binary mask + center of mass)
   - Extract center position
3. **Averaging**: 20 consecutive measurements averaged per control update
4. **PI control**: Computed correction applied to piezo Z-position
5. **Update rate**: 20 Hz control loop

### Key Parameters
- Control frequency: 20 Hz
- Averaging: user-adjustable (typically 20 frames per update)
- Max correction step: 0.2 μm
- Max drift before unlock: 15 μm
- Typical stability: ~8 nm (std dev)

## Optical Setup

<img width="1200" height="1600" alt="image" src="https://github.com/user-attachments/assets/3590047f-0f3b-480d-aed4-5e4354686db0" />

1. Pick-off mirror redirects reflected beam
2. Lens 1 (Focus beam on Iris)
3. Iris suppresses spurious reflections if needed
4. Lens 2 (Collimates beam after Iris)
5. Lens 3 (Focus Beam on webcam detector)
6. Webcam detector images beam spot


## Technical Details

- **Language**: Python 3.9
- **Camera interface**: OpenCV 4.8.0
- **Numerical processing**: NumPy 1.24.0, SciPy 1.11.0
- **Visualization**: PyQtGraph 0.13.0
- **Piezo control**: Mad City Labs NanoDrive DLL

## Citation

If you use this software in your research, please cite: ...

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request


## Troubleshooting

### Common Issues

**Problem**: Calibration shows non-linear relationship
- **Solution**: First adjust acquisition/detection parameters (digital gain, gamma correction, binarization threshold if using contour centroid). If linearity is not restored, adjust the HiLO/TIRF illumination angle, verify imaging depth is within the objective's working range, attenuate the beam with neutral density filters to avoid detector saturation, or partially close the iris.

**Problem**: System unlocks frequently
- **Solution**: Reduce Kp/Ki gains, verify illumination stability, check for vibrations

**Problem**: Large oscillations during lock
- **Solution**: Reduce Kp gain, ensure proper calibration

**Problem**: Contour centroid detection is unstable or noisy
- **Solution**: Adjust the binarization threshold, check digital gain/gamma settings, and verify the beam is not saturating or too dim on the sensor

**Problem**: Cannot find camera
- **Solution**: Check USB connection, verify camera index (default 0)

**Problem**: DLL not found
- **Solution**: Install Mad City Labs NanoDrive software, verify DLL path

See user_guide.md for detailed troubleshooting.
