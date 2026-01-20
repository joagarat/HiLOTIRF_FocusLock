# User Guide

## Getting Started

### First Time Setup

1. **Hardware connections**
   - Connect webcam via USB
   - Verify piezo is controlled by Mad City Labs software
   - Align optical path for back-reflection

2. **Software launch**
```bash
   python src/focus_lock.py
```

3. **Calibration** (required before first use)
   - See [calibration_guide.md](calibration_guide.md)

## Daily Operation

### Starting a Session

1. Launch software
2. Run calibration
3. Set PI parameters (Kp=-0.01, Ki=-0.001)
4. Click "Lock Focus"

### During Acquisition

- Monitor real-time position plot
- Check standard deviation stays <10 nm
- Log data if needed for analysis

### Ending Session

1. Click "Unlock Focus"
2. Save data if desired
3. Close software

## Advanced Usage

### Optimizing PI Parameters

Start conservative, then tune:
- Begin with Kp=-0.005, Ki=-0.0005
- Increase magnitude if response too slow
- Decrease if oscillations occur

### Manual Piezo Movement

Use for:
- Finding focus initially
- Testing system response
- Moving to different Z-positions

Enter value in nm, click "Move Piezo"

### Stability Measurements

1. Click "Calculate Std Dev"
2. Read stability from display
3. Click "Reset" to restart measurement if you change position

## Tips & Best Practices

- ✅ Calibrate at start of each session
- ✅ Wait for thermal equilibrium before locking
- ✅ Use minimum illumination intensity that gives good signal
- ✅ Lock focus before starting long acquisitions
- ⚠️ Don't adjust illumination angle while locked
- ⚠️ Avoid mechanical disturbances during operation
