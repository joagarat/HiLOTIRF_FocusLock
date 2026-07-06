# -*- coding: utf-8 -*-
"""
Focus Lock System
- Main window: RAW camera + segmentation mask + plot
- Controls window: sliders and mode selection
- Calibration window: scatter + linear fit (opens on calibration)
- Modes:
  * Contour centroid (moments)
  * Gaussian 1D (curve_fit)
  * Gaussian 2D (curve_fit) — downsampled x4 to avoid GUI freeze
- N-frame averaging + optional EMA smoothing
"""

import sys
import numpy as np
import cv2
import time
from ctypes import cdll, c_int, c_uint, c_double
import atexit
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from scipy.ndimage import gaussian_filter
from scipy.optimize import curve_fit
import csv


# ---------------------- Util: 1D Gaussian ----------------------
def gaussian_1d(x, amp, cen, wid):
    return amp * np.exp(-(x - cen) ** 2 / (2 * wid ** 2))


# ---------------------- Util: 2D Gaussian ----------------------
def gaussian_2d(xy, amp, x0, y0, sx, sy, offset):
    x, y = xy
    return (offset + amp * np.exp(
        -((x - x0) ** 2 / (2 * sx ** 2) + (y - y0) ** 2 / (2 * sy ** 2))
    )).ravel()


# ---------------------- Calibration Window ----------------------
class CalibrationWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Calibration (Signal vs Z)")
        self.setGeometry(220, 120, 720, 520)

        layout = QtWidgets.QVBoxLayout(self)

        self.plot = pg.PlotWidget()
        self.plot.setLabel('left', 'Signal (mode units)')
        self.plot.setLabel('bottom', 'Z (piezo)')
        self.plot.showGrid(x=True, y=True)
        layout.addWidget(self.plot)

        self.info = QtWidgets.QLabel("slope=?, intercept=?, points=0", self)
        layout.addWidget(self.info)

    def plotData(self, positions, signals, slope, intercept):
        self.plot.clear()
        self.plot.plot(positions, signals, pen=None, symbol='o', symbolSize=8)

        x = np.array(positions, dtype=float)
        y = slope * x + intercept
        self.plot.plot(x, y, pen=pg.mkPen('r', width=2))

        self.info.setText(f"slope={slope:.6g}  intercept={intercept:.6g}  points={len(positions)}")


# ---------------------- Controls Window ----------------------
class ControlWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controls")
        self.setGeometry(980, 120, 400, 860)

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(self._sep("Detection mode"))
        self.modeCombo = QtWidgets.QComboBox(self)
        self.modeCombo.addItems([
            "Contour centroid (moments)",
            "Gaussian 1D (curve_fit)",
            "Gaussian 2D (curve_fit)",
        ])
        layout.addWidget(self.modeCombo)

        layout.addWidget(self._sep("Stability"))
        layout.addWidget(QtWidgets.QLabel("Frame averaging (N frames per measurement):"))
        self.avgSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.avgSlider.setMinimum(1)
        self.avgSlider.setMaximum(30)
        self.avgSlider.setValue(7)
        layout.addWidget(self.avgSlider)
        self.avgLabel = QtWidgets.QLabel("N=7", self)
        layout.addWidget(self.avgLabel)

        layout.addWidget(QtWidgets.QLabel("EMA smoothing (alpha x100, 0 = no EMA):"))
        self.emaSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.emaSlider.setMinimum(0)
        self.emaSlider.setMaximum(100)
        self.emaSlider.setValue(25)
        layout.addWidget(self.emaSlider)
        self.emaLabel = QtWidgets.QLabel("alpha=0.25", self)
        layout.addWidget(self.emaLabel)

        layout.addWidget(self._sep("Gaussian 2D downsampling"))
        layout.addWidget(QtWidgets.QLabel("Downsample scale (Gaussian 2D only):"))
        self.g2dScaleSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.g2dScaleSlider.setMinimum(1)
        self.g2dScaleSlider.setMaximum(8)
        self.g2dScaleSlider.setValue(4)
        layout.addWidget(self.g2dScaleSlider)
        self.g2dScaleLabel = QtWidgets.QLabel("scale=4", self)
        layout.addWidget(self.g2dScaleLabel)

        layout.addWidget(self._sep("Digital controls (post-processing, all modes)"))
        layout.addWidget(QtWidgets.QLabel("Digital Gain (x100):"))
        self.gainSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.gainSlider.setMinimum(50)
        self.gainSlider.setMaximum(400)
        self.gainSlider.setValue(100)
        layout.addWidget(self.gainSlider)

        layout.addWidget(QtWidgets.QLabel("Gamma (x100):"))
        self.gammaSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.gammaSlider.setMinimum(50)
        self.gammaSlider.setMaximum(400)
        self.gammaSlider.setValue(100)
        layout.addWidget(self.gammaSlider)

        layout.addWidget(QtWidgets.QLabel("Soft Clip (0-255):"))
        self.clipSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.clipSlider.setMinimum(0)
        self.clipSlider.setMaximum(255)
        self.clipSlider.setValue(255)
        layout.addWidget(self.clipSlider)

        self.digitalLabel = QtWidgets.QLabel("gain=1.00  gamma=1.00  clip=255", self)
        layout.addWidget(self.digitalLabel)

        layout.addWidget(self._sep("Segmentation (contour centroid mode only)"))
        layout.addWidget(QtWidgets.QLabel("Threshold (0 = Otsu automatic):"))
        self.threshSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.threshSlider.setMinimum(0)
        self.threshSlider.setMaximum(255)
        self.threshSlider.setValue(0)
        layout.addWidget(self.threshSlider)

        layout.addWidget(QtWidgets.QLabel("Min Area (contour):"))
        self.minAreaSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.minAreaSlider.setMinimum(10)
        self.minAreaSlider.setMaximum(5000)
        self.minAreaSlider.setValue(200)
        layout.addWidget(self.minAreaSlider)

        self.segLabel = QtWidgets.QLabel("thresh=Otsu  minArea=200", self)
        layout.addWidget(self.segLabel)

        layout.addStretch(1)

        self.avgSlider.valueChanged.connect(self._updateLabels)
        self.emaSlider.valueChanged.connect(self._updateLabels)
        self.g2dScaleSlider.valueChanged.connect(self._updateLabels)
        self.gainSlider.valueChanged.connect(self._updateLabels)
        self.gammaSlider.valueChanged.connect(self._updateLabels)
        self.clipSlider.valueChanged.connect(self._updateLabels)
        self.threshSlider.valueChanged.connect(self._updateLabels)
        self.minAreaSlider.valueChanged.connect(self._updateLabels)

        self._updateLabels()

    def _sep(self, title):
        return QtWidgets.QLabel(f"<b>{title}</b>")

    def _updateLabels(self):
        self.avgLabel.setText(f"N={self.avgSlider.value()}")
        self.emaLabel.setText(f"alpha={self.emaSlider.value()/100.0:.2f}")
        self.g2dScaleLabel.setText(f"scale={self.g2dScaleSlider.value()}")

        dg = self.gainSlider.value() / 100.0
        gm = self.gammaSlider.value() / 100.0
        sc = self.clipSlider.value()
        self.digitalLabel.setText(f"gain={dg:.2f}  gamma={gm:.2f}  clip={sc}")

        th = self.threshSlider.value()
        th_txt = "Otsu" if th == 0 else str(th)
        ma = self.minAreaSlider.value()
        self.segLabel.setText(f"thresh={th_txt}  minArea={ma}")


# ---------------------- Piezo ----------------------
class Madpiezo:
    def __init__(self, path_to_dll):
        self.madlib = cdll.LoadLibrary(path_to_dll)
        self.handler = self.mcl_start()
        atexit.register(self.mcl_close)
        self.set_initial_z_position(50)

    def mcl_start(self):
        mcl_init_handle = self.madlib['MCL_InitHandle']
        mcl_init_handle.restype = c_int
        handler = mcl_init_handle()
        if handler == 0:
            print("MCL initialization error")
            return -1
        print("MCL initialized successfully, handler:", handler)
        return handler

    def set_initial_z_position(self, z_value):
        self.mcl_write(z_value, 3)

    def zPosition(self):
        return self.mcl_read(3)

    def zMoveRelative(self, value):
        current_z = self.zPosition()
        new_z = current_z + value
        if new_z < 0 or new_z > 100:
            print("Move out of bounds:", new_z)
            return
        self.mcl_write(new_z, 3)

    def mcl_read(self, axis_number):
        mcl_single_read_n = self.madlib['MCL_SingleReadN']
        mcl_single_read_n.restype = c_double
        return mcl_single_read_n(c_uint(axis_number), c_int(self.handler))

    def mcl_write(self, position, axis_number):
        mcl_single_write_n = self.madlib['MCL_SingleWriteN']
        mcl_single_write_n.restype = c_int
        err = mcl_single_write_n(c_double(position), c_uint(axis_number), c_int(self.handler))
        if err != 0:
            print("MCL write error =", err)
        return err

    def mcl_close(self):
        mcl_release_all = self.madlib['MCL_ReleaseAllHandles']
        mcl_release_all()
        print("MCL closed")


# ---------------------- PI ----------------------
class PI:
    def __init__(self, setpoint, kp=1.0, ki=0.0, max_output=None):
        self.setpoint = setpoint
        self.kp = kp
        self.ki = ki
        self.max_output = max_output
        self.integral = 0.0

    def update(self, measured_value):
        error = self.setpoint - measured_value
        self.integral += error
        output = self.kp * error + self.ki * self.integral
        if self.max_output is not None:
            output = max(min(output, self.max_output), -self.max_output)
        return output


# ---------------------- Main Window ----------------------
class FocusGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Focus Lock")
        self.setGeometry(80, 80, 1100, 760)

        self.ctrl = ControlWindow()
        self.calibWindow = CalibrationWindow()
        self.ctrl.show()

        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0, cv2.CAP_MSMF)

        self.focusSignal = 0.0
        self.madpiezo = None
        self.focusWorker = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        mainLayout = QtWidgets.QVBoxLayout(central)

        # Button row
        btnRow = QtWidgets.QHBoxLayout()
        self.lockButton = QtWidgets.QPushButton("Lock Focus")
        self.unlockButton = QtWidgets.QPushButton("Unlock Focus")
        self.calibrateButton = QtWidgets.QPushButton("Calibrate")
        self.saveDataCheckbox = QtWidgets.QCheckBox("Save Data")
        self.saveDataButton = QtWidgets.QPushButton("Save CSV")
        btnRow.addWidget(self.lockButton)
        btnRow.addWidget(self.unlockButton)
        btnRow.addWidget(self.calibrateButton)
        btnRow.addStretch(1)
        btnRow.addWidget(self.saveDataCheckbox)
        btnRow.addWidget(self.saveDataButton)
        mainLayout.addLayout(btnRow)

        # Kp/Ki + Move piezo + Controls
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Kp:"))
        self.kpEdit = QtWidgets.QLineEdit("0.0")
        self.kpEdit.setFixedWidth(80)
        row2.addWidget(self.kpEdit)

        row2.addWidget(QtWidgets.QLabel("Ki:"))
        self.kiEdit = QtWidgets.QLineEdit("0.0")
        self.kiEdit.setFixedWidth(80)
        row2.addWidget(self.kiEdit)

        row2.addSpacing(20)
        row2.addWidget(QtWidgets.QLabel("Move Piezo (nm):"))
        self.piezoMoveEdit = QtWidgets.QLineEdit()
        self.piezoMoveEdit.setFixedWidth(100)
        row2.addWidget(self.piezoMoveEdit)
        self.movePiezoButton = QtWidgets.QPushButton("Move")
        row2.addWidget(self.movePiezoButton)

        row2.addStretch(1)
        self.showControlsButton = QtWidgets.QPushButton("Controls…")
        row2.addWidget(self.showControlsButton)
        mainLayout.addLayout(row2)

        # Image panel + plot
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        imgPanel = QtWidgets.QWidget()
        imgLayout = QtWidgets.QVBoxLayout(imgPanel)
        imgLayout.setContentsMargins(0, 0, 0, 0)

        self.rawView = pg.ImageView()
        self.rawView.ui.roiBtn.hide()
        self.rawView.ui.menuBtn.hide()

        self.maskView = pg.ImageView()
        self.maskView.ui.roiBtn.hide()
        self.maskView.ui.menuBtn.hide()

        imgLayout.addWidget(QtWidgets.QLabel("RAW (with crosshair):"))
        imgLayout.addWidget(self.rawView, 1)
        imgLayout.addWidget(QtWidgets.QLabel("MASK (segmentation):"))
        imgLayout.addWidget(self.maskView, 1)

        splitter.addWidget(imgPanel)

        self.focusPlot = pg.PlotWidget()
        self.focusPlot.setLabel('left', 'Z relative (nm)')
        self.focusPlot.setLabel('bottom', 'samples')
        self.focusPlot.showGrid(x=True, y=True)
        splitter.addWidget(self.focusPlot)

        splitter.setSizes([700, 400])
        mainLayout.addWidget(splitter, 1)

        # Std row
        stdRow = QtWidgets.QHBoxLayout()
        self.startStdButton = QtWidgets.QPushButton("Compute Std")
        self.resetStdButton = QtWidgets.QPushButton("Reset Std")
        self.stdLabel = QtWidgets.QLabel("Standard deviation: 0.00 nm")
        stdRow.addWidget(self.startStdButton)
        stdRow.addWidget(self.resetStdButton)
        stdRow.addWidget(self.stdLabel)
        stdRow.addStretch(1)
        mainLayout.addLayout(stdRow)

        self.showControlsButton.clicked.connect(self.ctrl.show)

    def closeEvent(self, event):
        try:
            self.cap.release()
        except Exception:
            pass
        if self.focusWorker:
            self.focusWorker.focusTimer.stop()
        if self.madpiezo:
            self.madpiezo.mcl_close()
        event.accept()


# ---------------------- Worker ----------------------
class focusWorker(QtCore.QObject):
    def __init__(self, gui, actuator):
        super().__init__()
        self.gui = gui
        self.actuator = actuator

        self.locked = False

        self.npoints = 80
        self.ptr = 0
        self.data = np.zeros(self.npoints, dtype=float)

        self.scansPerS = 20
        self.focusTime = int(1000 / self.scansPerS)
        self.focusTimer = QtCore.QTimer()
        self.focusTimer.timeout.connect(self.update)
        self.focusTimer.start(self.focusTime)

        self.initialZ = self.actuator.zPosition()

        self.slope = None
        self.conversion_factor = None
        self.initial_signal = None
        self.setPoint = 0.0

        self.setupPI()

        self.filtered_signal = None

        self.calculating_std = False
        self.stdData = []
        self.startTime = time.time()

        self.stats = []
        self.saveStartTime = None

        self.zeroLine = None
        self.setpointLine = None

        self.gui.lockButton.clicked.connect(self.lockFocus)
        self.gui.unlockButton.clicked.connect(self.unlockFocus)
        self.gui.calibrateButton.clicked.connect(self.calibrate)
        self.gui.saveDataButton.clicked.connect(self.saveDataDialog)
        self.gui.movePiezoButton.clicked.connect(self.movePiezoFromGui)
        self.gui.startStdButton.clicked.connect(self.startStdCalculation)
        self.gui.resetStdButton.clicked.connect(self.resetStdCalculation)

    # ---------- UI helpers ----------
    def saveDataDialog(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self.gui, "Save CSV", "", "CSV Files (*.csv)")
        if filename:
            self.saveStatsToCSV(filename)

    def movePiezoFromGui(self):
        txt = self.gui.piezoMoveEdit.text().strip()
        if not txt:
            return
        try:
            move_value = float(txt) / 1000.0
            self.actuator.zMoveRelative(move_value)
        except ValueError:
            print("Move Piezo: invalid value")

    # ---------- Digital controls ----------
    def applyDigitalControls(self, frame_bgr):
        ctrl = self.gui.ctrl
        dg = ctrl.gainSlider.value() / 100.0
        gm = ctrl.gammaSlider.value() / 100.0
        sc = ctrl.clipSlider.value()

        x = frame_bgr.astype(np.float32)

        if sc < 255:
            x = np.minimum(x, float(sc))

        x *= float(dg)
        x = np.clip(x, 0, 255)

        gm = max(float(gm), 1e-6)
        xn = (x / 255.0) ** (1.0 / gm)
        out = (xn * 255.0).astype(np.uint8)
        return out

    # ---------- Segmentation mask (contour centroid only) ----------
    def make_work_mask(self, img_u8):
        ctrl = self.gui.ctrl
        img = gaussian_filter(img_u8, sigma=1).astype(np.uint8)
        thresh_val = int(ctrl.threshSlider.value())

        if thresh_val == 0:
            _, work = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        else:
            _, work = cv2.threshold(img, thresh_val, 255, cv2.THRESH_BINARY)

        kernel = np.ones((5, 5), np.uint8)
        work = cv2.morphologyEx(work, cv2.MORPH_CLOSE, kernel)
        return work

    # ---------- Detection modes ----------
    def measure_contour_centroid(self, blue_u8, work):
        ctrl = self.gui.ctrl

        kernel = np.ones((3, 3), np.uint8)
        clean = cv2.morphologyEx(work, cv2.MORPH_OPEN, kernel)
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None, blue_u8

        c = max(contours, key=cv2.contourArea)

        if cv2.contourArea(c) < int(ctrl.minAreaSlider.value()):
            return None, blue_u8

        M = cv2.moments(c)

        if M["m00"] == 0:
            return None, blue_u8

        cx = float(M["m10"] / M["m00"])
        cy = float(M["m01"] / M["m00"])

        dbg = blue_u8.copy()
        x = int(round(cx))
        y = int(round(cy))

        if 2 <= x < dbg.shape[1]-2 and 2 <= y < dbg.shape[0]-2:
            dbg[y, x-2:x+3] = 255
            dbg[y-2:y+3, x] = 255

        return cx, dbg

    def measure_gaussian_1d(self, blue_u8):
        h, w = blue_u8.shape
        y0 = h // 2

        band = max(5, h // 40)
        y1 = max(0, y0 - band // 2)
        y2 = min(h, y0 + band // 2 + 1)

        prof = blue_u8[y1:y2, :].astype(np.float32).mean(axis=0)
        prof = gaussian_filter(prof, sigma=1)

        x = np.arange(w, dtype=np.float32)

        mask = prof < 250
        if mask.mean() < 0.8:
            return None, blue_u8

        xp = x[mask]
        yp = prof[mask]

        amp0 = float(yp.max() - yp.min())
        cen0 = float(xp[np.argmax(yp)])
        wid0 = 10.0

        try:
            popt, _ = curve_fit(gaussian_1d, xp, yp, p0=[amp0, cen0, wid0], maxfev=2000)
            cen = float(popt[1])
        except Exception:
            return None, blue_u8

        dbg = blue_u8.copy()
        xi = int(round(cen))
        yi = y0
        if 2 <= xi < w-2 and 2 <= yi < h-2:
            dbg[yi, xi-2:xi+3] = 255
            dbg[yi-2:yi+3, xi] = 255
        return cen, dbg

    def measure_gaussian_2d(self, blue_u8):
        """
        2D Gaussian fit on a downsampled image to avoid freezing the GUI.
        The fitted centroid is rescaled back to original pixel coordinates.
        """
        ctrl = self.gui.ctrl
        scale = max(1, int(ctrl.g2dScaleSlider.value()))

        h0, w0 = blue_u8.shape

        small = cv2.resize(blue_u8, (w0 // scale, h0 // scale), interpolation=cv2.INTER_AREA)
        h, w = small.shape
        img = gaussian_filter(small.astype(np.float32), sigma=2)

        total = img.sum()
        if total == 0:
            return None, blue_u8

        xs = np.arange(w, dtype=np.float32)
        ys = np.arange(h, dtype=np.float32)
        X, Y = np.meshgrid(xs, ys)

        x0 = float((X * img).sum() / total)
        y0 = float((Y * img).sum() / total)
        amp0 = float(img.max() - img.min())
        sx0 = 10.0
        sy0 = 10.0
        off0 = float(img.min())

        try:
            popt, _ = curve_fit(
                gaussian_2d,
                (X.ravel(), Y.ravel()),
                img.ravel(),
                p0=[amp0, x0, y0, sx0, sy0, off0],
                maxfev=3000,
                bounds=(
                    [0,    0,  0,  1,  1,   0],
                    [255,  w,  h, w/2, h/2, 255]
                )
            )
            cx = float(popt[1]) * scale
            cy = float(popt[2]) * scale
        except Exception:
            return None, blue_u8

        dbg = blue_u8.copy()
        xi = int(round(cx))
        yi = int(round(cy))
        if 2 <= xi < w0-2 and 2 <= yi < h0-2:
            dbg[yi, xi-2:xi+3] = 255
            dbg[yi-2:yi+3, xi] = 255

        return cx, dbg

    def measure_signal(self, blue_u8, work):
        mode = self.gui.ctrl.modeCombo.currentText()
        if mode.startswith("Contour"):
            return self.measure_contour_centroid(blue_u8, work)
        if mode.startswith("Gaussian 1D"):
            return self.measure_gaussian_1d(blue_u8)
        if mode.startswith("Gaussian 2D"):
            return self.measure_gaussian_2d(blue_u8)
        return self.measure_contour_centroid(blue_u8, work)

    # ---------- PI ----------
    def setupPI(self):
        try:
            kp = float(self.gui.kpEdit.text())
        except ValueError:
            kp = 0.0
        try:
            ki = float(self.gui.kiEdit.text())
        except ValueError:
            ki = 0.0
        self.pi_controller = PI(setpoint=self.setPoint, kp=kp, ki=ki, max_output=0.2)

    def reset(self):
        self.data[:] = 0.0
        self.ptr = 0
        self.stats = []
        self.initial_signal = None
        self.filtered_signal = None
        self.startTime = time.time()
        self.saveStartTime = None

    def lockFocus(self):
        self.locked = True
        self.initialZ = self.actuator.zPosition()

        self.setupPI()
        self.setPoint = self.gui.focusSignal
        self.pi_controller.setpoint = self.setPoint

        self.filtered_signal = None
        self.reset()
        print("Focus locked")

    def unlockFocus(self):
        self.locked = False
        self.reset()
        print("Focus unlocked")

    def updatePI(self):
        cm = self.gui.focusSignal
        out = self.pi_controller.update(cm)

        max_step = 0.2
        max_distance = 15

        if abs(out) > max_step:
            out = np.sign(out) * max_step

        current_z = self.actuator.zPosition()
        distance = current_z - self.initialZ

        if abs(distance) > max_distance or current_z < 0 or current_z > 100:
            self.unlockFocus()
        else:
            self.actuator.zMoveRelative(out)

    def updatePlotLines(self):
        x_axis = np.arange(len(self.data))
        if self.zeroLine is None:
            self.zeroLine = self.gui.focusPlot.plot(x_axis, [0.0]*len(self.data), pen=(80, 80, 80))
        else:
            self.zeroLine.setData(x_axis, [0.0]*len(self.data))

        if self.locked and self.conversion_factor is not None and self.initial_signal is not None:
            corrected_setpoint_nm = (self.setPoint - self.initial_signal) * self.conversion_factor
            if self.setpointLine is None:
                self.setpointLine = self.gui.focusPlot.plot(
                    x_axis, [corrected_setpoint_nm]*len(self.data),
                    pen=(255, 0, 255), width=3
                )
            else:
                self.setpointLine.setData(x_axis, [corrected_setpoint_nm]*len(self.data))

    # ---------- Main loop ----------
    def update(self):
        ctrl = self.gui.ctrl
        N = int(ctrl.avgSlider.value())
        alpha = ctrl.emaSlider.value() / 100.0

        sum_signal = 0.0
        count = 0

        raw_dbg = None
        mask_dbg = None

        for _ in range(N):
            ret, frame = self.gui.cap.read()
            if not ret:
                continue

            proc = self.applyDigitalControls(frame)
            blue = proc[:, :, 0].astype(np.uint8)

            work = self.make_work_mask(blue)

            s, dbg = self.measure_signal(blue, work)
            if dbg is not None:
                raw_dbg = dbg
            mask_dbg = work

            if s is None:
                continue

            sum_signal += float(s)
            count += 1

        if raw_dbg is not None:
            self.gui.rawView.setImage(raw_dbg.T, autoLevels=False)
        if mask_dbg is not None:
            self.gui.maskView.setImage(mask_dbg.T, autoLevels=True)

        if count == 0:
            return

        raw_signal = sum_signal / count

        if alpha <= 0.0:
            filtered = raw_signal
        else:
            if self.filtered_signal is None:
                self.filtered_signal = raw_signal
            else:
                self.filtered_signal = alpha * raw_signal + (1.0 - alpha) * self.filtered_signal
            filtered = self.filtered_signal

        self.gui.focusSignal = float(filtered)

        if self.slope is None or self.slope == 0:
            return

        self.conversion_factor = (-1.0 / (self.slope / 1000.0)) if self.slope != 0 else None
        if self.conversion_factor is None:
            return

        if self.initial_signal is None:
            self.initial_signal = float(filtered)

        relative_nm = (float(filtered) - self.initial_signal) * self.conversion_factor

        if self.ptr < self.npoints:
            self.data[self.ptr] = relative_nm
        else:
            self.data[:-1] = self.data[1:]
            self.data[-1] = relative_nm
        self.ptr += 1

        self.gui.focusPlot.plot(self.data, clear=True)
        self.updatePlotLines()

        if self.locked:
            self.updatePI()

        if self.calculating_std:
            self.stdData.append(relative_nm)
            if len(self.stdData) > 1 and time.time() - self.startTime >= 1:
                std_dev = np.std(self.stdData)
                self.gui.stdLabel.setText(f"Standard deviation: {std_dev:.2f} nm")
                self.startTime = time.time()

        if self.gui.saveDataCheckbox.isChecked():
            if self.saveStartTime is None:
                self.saveStartTime = time.time()
            t = time.time() - self.saveStartTime

            mode = ctrl.modeCombo.currentText()
            dg = ctrl.gainSlider.value() / 100.0
            gm = ctrl.gammaSlider.value() / 100.0
            sc = ctrl.clipSlider.value()
            th = ctrl.threshSlider.value()
            ma = ctrl.minAreaSlider.value()

            self.stats.append((t, relative_nm, raw_signal, filtered, N, alpha, mode, dg, gm, sc, th, ma))
        else:
            self.saveStartTime = None

    # ---------- Calibration ----------
    def calibrate(self):
        initial_z = self.actuator.zPosition()
        positions = []
        signals = []

        ctrl = self.gui.ctrl
        N = int(ctrl.avgSlider.value())

        alpha_saved = ctrl.emaSlider.value()
        ctrl.emaSlider.setValue(0)
        self.filtered_signal = None

        for i in range(10):
            self.actuator.zMoveRelative(0.06)
            time.sleep(1)

            s_acc = 0.0
            n = 0
            raw_dbg = None
            mask_dbg = None

            for _ in range(N * 6):
                ret, frame = self.gui.cap.read()
                if not ret:
                    continue

                proc = self.applyDigitalControls(frame)
                blue = proc[:, :, 0].astype(np.uint8)
                work = self.make_work_mask(blue)

                s, dbg = self.measure_signal(blue, work)
                raw_dbg = dbg if dbg is not None else raw_dbg
                mask_dbg = work

                if s is None:
                    continue
                s_acc += float(s)
                n += 1

            if raw_dbg is not None:
                self.gui.rawView.setImage(raw_dbg.T, autoLevels=False)
            if mask_dbg is not None:
                self.gui.maskView.setImage(mask_dbg.T, autoLevels=True)

            if n == 0:
                print("Calibration: no valid detections. Adjust threshold/minArea or change mode.")
                continue

            avg_s = s_acc / n
            positions.append(float(self.actuator.zPosition()))
            signals.append(float(avg_s))
            print(f"Calibration - Position: {positions[-1]:.4f}, Signal: {avg_s:.6f}")

        self.actuator.mcl_write(initial_z, 3)

        ctrl.emaSlider.setValue(alpha_saved)
        self.filtered_signal = None

        if len(positions) >= 2:
            m, b = np.polyfit(positions, signals, 1)
            self.slope = float(m)
            print(f"Linear fit signal vs Z: slope={m}, intercept={b}")

            self.gui.calibWindow.plotData(positions, signals, float(m), float(b))
            self.gui.calibWindow.show()
            self.gui.calibWindow.raise_()
            self.gui.calibWindow.activateWindow()
        else:
            print("Calibration failed: insufficient valid points.")

    # ---------- CSV ----------
    def saveStatsToCSV(self, filename):
        with open(filename, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow([
                "t(s)", "Z_rel(nm)", "signal_raw", "signal_filtered",
                "AvgN", "EMA_alpha", "Mode",
                "gain", "gamma", "soft_clip",
                "thresh", "minArea"
            ])
            w.writerows(self.stats)
        print("Data saved to", filename)

    # ---------- Std ----------
    def resetStdCalculation(self):
        self.stdData = []
        self.calculating_std = True
        self.startTime = time.time()

    def startStdCalculation(self):
        self.stdData = []
        self.calculating_std = True
        self.startTime = time.time()


# ---------------------- Main ----------------------
def main():
    path_to_dll = r'C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll'

    app = QtWidgets.QApplication(sys.argv)
    ex = FocusGUI()
    ex.madpiezo = Madpiezo(path_to_dll)
    ex.focusWorker = focusWorker(ex, ex.madpiezo)
    ex.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()