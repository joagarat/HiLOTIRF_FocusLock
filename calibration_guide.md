# Calibration Guide

## Overview
Calibration establishes the linear relationship between lateral beam displacement (pixels) and axial position (micrometers).

## Procedure

1. **Prepare system**
   - Ensure stable illumination
   - Verify back-reflection is visible on webcam
   - Check piezo is at mid-range (~50 μm)

2. **Run calibration**
   - Click "Calibrate" button
   - System automatically:
     - Moves piezo 10 steps of 60 nm
     - Acquires 20 frames per position
     - Detects beam position on each frame
     - Averages measurements

3. **Verify calibration**
   - Calibration plot window opens
   - Check for linear relationship 
   - Slope value printed to console

## Expected Results

![Calibration curve](https://github.com/user-attachments/assets/61a2d0e6-6d2b-4eac-9c61-76a83ecbae80)

**Good calibration:**
- Linear fit 
- Minimal scatter around fit line

**Poor calibration (non-linear):**
- Curved or scattered points
- Indicates optical problems

## Troubleshooting Non-linear Calibrations

### Detector Saturation
- **Solution**: Add neutral density filter to reflected beam

### Wrong Imaging Depth
- **Solution**: Adjust sample axial position to working range

### Suboptimal Reflection Angle
- **Solution**: Adjust HiLO/TIRF illumination angle

### Spurious Reflections
- **Solution**: Use iris to block unwanted reflections
