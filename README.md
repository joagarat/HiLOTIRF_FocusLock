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

2. **Calibrate** before first use:
   - Click "Calibrate" button
   - System will move piezo through 10 steps of 60 nm
   - Linear  curve will be displayed
   - Only if Linear relationship is detected continue. If there is no linear relationship adjust optics (consider adding density filter before webca, adjusting HiLO or TIRF illumination angle, centering the beam onto the webcam, etc).

3. **Lock focus**:
   - Adjust Kp and Ki parameters (On our system: Kp=-0.01, Ki=-0.001)
   - Click "Lock Focus"
   - Monitor stability in real-time plot
   - If focus lock is not working consider optimizing Kp and Ki to your system.

4. **Monitor stability**:
   - Click "Calculate Std Dev" to measure fluctuations
   - Enable "Save Data" to log position over time

## Usage Guide

### PI Controller Parameters

- **Kp (Proportional gain)**: Typical value -0.01
  - More negative = stronger immediate response
  - Too high → oscillations
  
- **Ki (Integral gain)**: Typical value -0.001
  - Eliminates steady-state error
  - Too high → instability

### 

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
   - Fit Gaussian to beam profile
   - Extract center position
3. **Averaging**: 20 consecutive measurements averaged per control update
4. **PI control**: Computed correction applied to piezo Z-position
5. **Update rate**: 20 Hz control loop

### Key Parameters
- Control frequency: 20 Hz
- Averaging: 20 frames per update
- Max correction step: 0.2 μm
- Max drift before unlock: 15 μm
- Typical stability: ~8 nm (std dev)

## Optical Setup

<img width="1200" height="1600" alt="image" src="https://github.com/user-attachments/assets/3590047f-0f3b-480d-aed4-5e4354686db0" />

1. Pick-off mirror redirects reflected beam
2. Lens 1 (Focus beam on Iris)
3. Iris suppresses spurious reflections
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

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

## Troubleshooting

### Common Issues

**Problem**: Calibration shows non-linear relationship
- **Solution**: Adjust HiLO/TIRF angle, verify imaging depth, check for detector saturation

**Problem**: System unlocks frequently
- **Solution**: Reduce Kp/Ki gains, verify illumination stability, check for vibrations

**Problem**: Large oscillations during lock
- **Solution**: Reduce Kp gain, ensure proper calibration

**Problem**: Cannot find camera
- **Solution**: Check USB connection, verify camera index (default 0)

**Problem**: DLL not found
- **Solution**: Install Mad City Labs NanoDrive software, verify DLL path

See user_guide.md for detailed troubleshooting.

## Contact

Joaquin Garat   
joagarat@gmail.com
Departamento de Genómica, Instituto de Investigaciones Biológicas Clemente Estable, Montevideo, Uruguay.

## Acknowledgments

- 
- 
