# -*- coding: utf-8 -*-
"""
Created on Thu Sep 26 16:58:17 2024

@author: User
"""

import sys
import numpy as np
import cv2
import time
from ctypes import cdll, c_int, c_uint, c_double
import atexit
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter
import csv

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
            print("Error de inicialización de MCL")
            return -1
        print("MCL inicializado con éxito, handler:", handler)
        return handler

    def set_initial_z_position(self, z_value):
        self.mcl_write(z_value, 3)
        print(f"Posición Z inicial establecida en {z_value}")

    def zPosition(self):
        pos = self.mcl_read(3)
        print("Posición Z actual:", pos)
        return pos

    def zMoveRelative(self, value):
        current_z = self.zPosition()
        new_z = current_z + value
        if new_z < 0 or new_z > 100:
            print("Movimiento fuera de los límites: ", new_z)
            return
        
        self.mcl_write(new_z, 3)
        print(f"Movido a Z = {new_z}")

    def mcl_read(self, axis_number):
        mcl_single_read_n = self.madlib['MCL_SingleReadN']
        mcl_single_read_n.restype = c_double
        pos = mcl_single_read_n(c_uint(axis_number), c_int(self.handler))
        print(f"Leído {pos} del eje {axis_number}")
        return pos

    def mcl_write(self, position, axis_number):
        mcl_single_write_n = self.madlib['MCL_SingleWriteN']
        mcl_single_write_n.restype = c_int
        error_code = mcl_single_write_n(c_double(position), c_uint(axis_number), c_int(self.handler))
        if error_code != 0:
            print("Error de escritura en MCL = ", error_code)
        else:
            print(f"Escrito {position} en el eje {axis_number} con éxito")
        return error_code

    def mcl_close(self):
        mcl_release_all = self.madlib['MCL_ReleaseAllHandles']
        mcl_release_all()
        print("MCL cerrado")

def gaussian(x, amp, cen, wid):
    return amp * np.exp(-(x-cen)**2 / (2*wid**2))

class PI:
    def __init__(self, setpoint, kp=1.0, ki=0.0, max_output=None):
        self.setpoint = setpoint
        self.kp = kp
        self.ki = ki
        self.max_output = max_output
        self.integral = 0
        self.prev_error = 0

    def update(self, measured_value):
        error = self.setpoint - measured_value
        self.integral += error
        output = self.kp * error + self.ki * self.integral
        
        if self.max_output is not None:
            output = max(min(output, self.max_output), -self.max_output)
        
        return output

class FocusGUI(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.focusSignal = 0
        self.cap = cv2.VideoCapture(0)
        self.madpiezo = None  
        self.focusWorker = None  

    def initUI(self):
        self.setWindowTitle('Focus Lock System')
        self.setGeometry(100, 100, 1200, 800)

        mainWidget = QtWidgets.QWidget()
        self.setCentralWidget(mainWidget)
        self.mainLayout = QtWidgets.QGridLayout(mainWidget)

        # Widgets principales
        self.img = pg.ImageView()
        self.focusPlot = pg.PlotWidget()
        self.focusPlot.setLabel('left', 'Posición relativa (nm)')
        self.focusPlot.setLabel('bottom', 'Muestras')
        self.focusPlot.showGrid(x=True, y=True)
        
        self.mainLayout.addWidget(self.img, 0, 0, 1, 1)
        self.mainLayout.addWidget(self.focusPlot, 1, 0, 2, 1)

        # Panel de controles
        controls_layout = QtWidgets.QVBoxLayout()
        
        def create_groupbox(title, layout):
            box = QtWidgets.QGroupBox(title)
            box.setLayout(layout)
            return box

        # Control PI
        pi_layout = QtWidgets.QFormLayout()
        self.kpEdit = QtWidgets.QLineEdit(self)
        self.kpEdit.setText("0.0")
        self.kiEdit = QtWidgets.QLineEdit(self)
        self.kiEdit.setText("0.0")
        pi_layout.addRow("Kp:", self.kpEdit)
        pi_layout.addRow("Ki:", self.kiEdit)
        controls_layout.addWidget(create_groupbox("Control PI", pi_layout))

        # Acciones principales
        actions_layout = QtWidgets.QVBoxLayout()
        self.lockButton = QtWidgets.QPushButton('Lock Focus', self)
        self.unlockButton = QtWidgets.QPushButton('Unlock Focus', self)
        actions_layout.addWidget(self.lockButton)
        actions_layout.addWidget(self.unlockButton)
        controls_layout.addWidget(create_groupbox("Acciones Principales", actions_layout))

        # Calibración y movimiento
        calib_layout = QtWidgets.QVBoxLayout()
        self.calibrateButton = QtWidgets.QPushButton('Calibrate', self)
        move_layout = QtWidgets.QHBoxLayout()
        self.piezoMoveEdit = QtWidgets.QLineEdit(self)
        self.movePiezoButton = QtWidgets.QPushButton('Move Piezo (nm)', self)
        move_layout.addWidget(self.piezoMoveEdit)
        move_layout.addWidget(self.movePiezoButton)
        calib_layout.addWidget(self.calibrateButton)
        calib_layout.addLayout(move_layout)
        controls_layout.addWidget(create_groupbox("Calibración y Movimiento Manual", calib_layout))

        # Medición de estabilidad
        std_layout = QtWidgets.QVBoxLayout()
        self.startStdButton = QtWidgets.QPushButton('Calcular Desvío Estándar', self)
        self.resetStdButton = QtWidgets.QPushButton('Reset Std Calculation', self)
        self.stdLabel = QtWidgets.QLabel('Desvío estándar: 0.0 nm', self)
        self.stdLabel.setAlignment(QtCore.Qt.AlignCenter)
        std_layout.addWidget(self.startStdButton)
        std_layout.addWidget(self.resetStdButton)
        std_layout.addWidget(self.stdLabel)
        controls_layout.addWidget(create_groupbox("Medición de Estabilidad", std_layout))

        # Guardado de datos
        save_layout = QtWidgets.QVBoxLayout()
        self.saveDataCheckbox = QtWidgets.QCheckBox('Save Data', self)
        self.saveDataButton = QtWidgets.QPushButton('Save Data to CSV', self)
        save_layout.addWidget(self.saveDataCheckbox)
        save_layout.addWidget(self.saveDataButton)
        controls_layout.addWidget(create_groupbox("Guardado de Datos", save_layout))

        controls_layout.addStretch()
        self.mainLayout.addLayout(controls_layout, 0, 1, 3, 1)
        self.mainLayout.setColumnStretch(0, 3)
        self.mainLayout.setColumnStretch(1, 1)

        # Conectar señales
        self.lockButton.clicked.connect(self.lockFocus)
        self.unlockButton.clicked.connect(self.unlockFocus)
        self.saveDataButton.clicked.connect(self.saveDataToCSV)
        self.calibrateButton.clicked.connect(self.calibrate)
        self.movePiezoButton.clicked.connect(self.movePiezo)
        self.startStdButton.clicked.connect(self.startStdMeasurement)
        self.resetStdButton.clicked.connect(self.resetStdCalculation)
  
    def resetStdCalculation(self):
        if self.focusWorker:
            self.focusWorker.resetStdCalculation()
            
    def startStdMeasurement(self):
        if self.focusWorker:
            self.focusWorker.startStdCalculation()

    def lockFocus(self):
        if self.focusWorker:
            self.focusWorker.lockFocus()

    def unlockFocus(self):
        if self.focusWorker:
            self.focusWorker.unlockFocus()

    def saveDataToCSV(self):
        if self.focusWorker:
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar archivo CSV", "", "CSV Files (*.csv)")
            if filename:
                self.focusWorker.saveStatsToCSV(filename)

    def calibrate(self):
        if self.focusWorker:
            self.focusWorker.calibrate()

    def movePiezo(self):
        if self.focusWorker and self.piezoMoveEdit.text():
            try:
                move_value = float(self.piezoMoveEdit.text()) / 1000
                self.focusWorker.movePiezo(move_value)
            except ValueError:
                print("Por favor, ingrese un valor válido para el movimiento del piezo.")

    def closeEvent(self, event):
        self.cap.release()
        if self.focusWorker:
            self.focusWorker.focusTimer.stop()
        if self.madpiezo:
            self.madpiezo.mcl_close()
        event.accept()

class focusWorker(QtCore.QObject):
    def __init__(self, gui, actuator, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gui = gui
        self.actuator = actuator
        self.locked = False
        self.npoints = 50
        self.scansPerS = 20
        self.focusTime = int(1000 / self.scansPerS)
        self.focusTimer = QtCore.QTimer()
        self.focusTimer.timeout.connect(self.update)
        self.focusTimer.start(self.focusTime)
        self.currentZ = self.actuator.zPosition()
        self.initialZ = self.currentZ
        self.ptr = 0  
        self.initialFocus = 0.0
        self.initialFocusLine = None
        self.setPoint = 0.0  
        self.setpointLine = None  
        self.slope = None
        self.setupPI()
        self.reset()
        self.correction_factor = 0.005
        self.calibrating = False
        self.conversion_factor = None
        self.stats = []
        self.calculating_std = False
        self.initial_gaussian_pos_nm = None
        self.saveStartTime = None
        self.stdData = []
        self.calibration_plot_window = None

    def setupPI(self):
        self.setPoint = self.gui.focusSignal  

        try:
            kp = float(self.gui.kpEdit.text())
        except ValueError:
            kp = 0.0  

        try:
            ki = float(self.gui.kiEdit.text())
        except ValueError:
            ki = 0.0  

        self.pi_controller = PI(
            self.setPoint,
            kp=kp,
            ki=ki,
            max_output=0.2  
        )
        self.initialZ = self.currentZ
        self.updateSetpointLine()  

    def updatePI(self):
        self.distance = self.currentZ - self.initialZ
        cm = self.gui.focusSignal
        out = self.pi_controller.update(cm)

        max_step = 0.2  
        max_distance = 15  

        if abs(out) > max_step:
            out = np.sign(out) * max_step

        if abs(self.distance) > max_distance or self.currentZ < 0 or self.currentZ > 100:
            self.unlockFocus()
        else:
            self.actuator.zMoveRelative(out)

    def reset(self):
        self.data = np.zeros(self.npoints)
        self.ptr = 0
        self.startTime = time.time()
        self.stats = []  

    def update(self):
        avg_signal = 0.0
        num_acquisitions = 20
    
        ret, first_frame = self.gui.cap.read()
        if not ret:
            return
    
        blue_channel = first_frame[:, :, 0]  
        blue_channel = gaussian_filter(blue_channel, sigma=1)
        self.gui.img.setImage(blue_channel.T, autoLevels=False)
    
        for _ in range(num_acquisitions):
            ret, frame = self.gui.cap.read()
            if not ret:
                return
    
            blue_channel = frame[:, :, 0]
            blue_channel = gaussian_filter(blue_channel, sigma=1)
    
            height, width = blue_channel.shape
            center_line = height // 2
            profile = blue_channel[center_line, :]
            x = np.arange(profile.size)
    
            try:
                popt, _ = curve_fit(gaussian, x, profile, p0=[profile.max(), profile.argmax(), 10])
                signal = popt[1]
                avg_signal += signal
            except RuntimeError:
                print(f"Error en el ajuste gaussiano para la línea central")
    
        avg_signal /= num_acquisitions
        self.gui.focusSignal = avg_signal
    
        if self.slope is None or self.slope == 0:
            print("Error: Slope no definido. No se puede graficar sin una calibración previa.")
            return
    
        self.conversion_factor = (-1.0/(self.slope/1000)) if self.slope != 0 else None
        if self.conversion_factor is None:
            print("Error: Factor de conversión no definido o pendiente inválida.")
            return
    
        gaussian_pos_nm = avg_signal * self.conversion_factor
    
        if self.ptr == 0:
            self.initial_gaussian_pos_nm = gaussian_pos_nm
    
        relative_gaussian_pos_nm = gaussian_pos_nm - self.initial_gaussian_pos_nm
    
        if self.ptr < self.npoints:
            self.data[self.ptr] = relative_gaussian_pos_nm
        else:
            self.data[:-1] = self.data[1:]
            self.data[-1] = relative_gaussian_pos_nm
    
        self.ptr += 1
    
        self.gui.focusPlot.plot(self.data, clear=True)
        self.updateSetpointLine()
        self.updateInitialFocusLine()
    
        if self.locked:
            self.updatePI()
            
        if self.gui.saveDataCheckbox.isChecked():
            if self.saveStartTime is None:
                self.saveStartTime = time.time()
            
            current_time = time.time() - self.saveStartTime
            
            self.stats.append((current_time, relative_gaussian_pos_nm))
            print(f"Datos guardados: Tiempo={current_time:.2f}s, Señal de enfoque relativa en Z={relative_gaussian_pos_nm} nm")
        else:
            self.saveStartTime = None
    
        if self.calculating_std:
            self.stdData.append(relative_gaussian_pos_nm)
    
            if len(self.stdData) > 1 and time.time() - self.startTime >= 1:
                std_dev = np.std(self.stdData)
                print(f"Desvío estándar de la posición del foco: {std_dev} nm")
                self.gui.stdLabel.setText(f'Desvío estándar: {std_dev:.2f} nm')
                self.startTime = time.time()

    def movePiezo(self, move_value):
        self.actuator.zMoveRelative(move_value)

    def lockFocus(self):
        self.locked = True
        self.currentZ = self.actuator.zPosition()
        self.initialZ = self.currentZ
        self.setPoint = self.gui.focusSignal  
        self.initialFocus = self.setPoint    
        self.setupPI()
        self.reset()
        print("Enfoque bloqueado")
        self.updateSetpointLine()
        self.updateInitialFocusLine()  

    def updateInitialFocusLine(self):
        if self.initialFocusLine is None:
            self.initialFocusLine = self.gui.focusPlot.plot([0, self.ptr], [self.initialFocus, self.initialFocus], pen=(255, 255, 0))
        else:
            self.initialFocusLine.setData([0, self.ptr], [self.initialFocus, self.initialFocus])

    def unlockFocus(self):
        self.locked = False
        self.reset()
        print("Enfoque desbloqueado")

    def updateSetpointLine(self):
        if self.locked:
            corrected_setpoint = (self.setPoint * self.conversion_factor) - self.initial_gaussian_pos_nm
            x_axis_range = np.arange(len(self.data))
            
            if self.setpointLine is None:
                self.setpointLine = self.gui.focusPlot.plot(x_axis_range, [corrected_setpoint] * len(self.data), pen=(255, 0, 255), width=3)
            else:
                self.setpointLine.setData(x_axis_range, [corrected_setpoint] * len(self.data))

    def calibrate(self):
        initial_z = self.actuator.zPosition()
        positions = []
        signals = []
    
        for i in range(10):
            self.actuator.zMoveRelative(0.06)
            time.sleep(1)
    
            avg_signal = 0.0
            for _ in range(20):
                ret, frame = self.gui.cap.read()
                if not ret:
                    return
    
                blue_channel = frame[:, :, 0]
                blue_channel = gaussian_filter(blue_channel, sigma=1)
                height, width = blue_channel.shape
                center_line = height // 2
                profile = blue_channel[center_line, :]
                x = np.arange(profile.size)
                try:
                    popt, _ = curve_fit(gaussian, x, profile, p0=[profile.max(), profile.argmax(), 10])
                    signal = popt[1]
                    avg_signal += signal
                except RuntimeError:
                    print("Error en el ajuste gaussiano para la línea central")
            
            avg_signal /= 20
            positions.append(self.actuator.zPosition())
            signals.append(avg_signal)
            print(f"Calibración - Posición: {positions[-1]}, Señal promedio: {avg_signal}")
    
        self.actuator.mcl_write(initial_z, 3)
    
        self.calibration_data = {
            'positions': positions,
            'signals': signals
        }
    
        self.plotCalibrationData(positions, signals)

    def plotCalibrationData(self, positions, signals):
        if self.calibration_plot_window is None:
            self.calibration_plot_window = pg.plot(title="Curva de Calibración")
            self.calibration_plot_window.setLabel('left', 'Señal de Enfoque')
            self.calibration_plot_window.setLabel('bottom', 'Posición Z (micras)')
            self.calibration_plot_window.showGrid(x=True, y=True)
        
        self.calibration_plot_window.clear()
        self.calibration_plot_window.plot(positions, signals, pen=None, symbol='o', symbolBrush='g')
        
        if len(positions) >= 2:
            m, b = np.polyfit(positions, signals, 1)
            fit_line_x = np.array(positions)
            fit_line_y = m * fit_line_x + b
            self.calibration_plot_window.plot(fit_line_x, fit_line_y, pen='r')
            print(f"Ajuste lineal: pendiente={m}, intercepto={b}")
            self.slope = m
            print(f"Pendiente guardada en self.slope: {self.slope}")
            conversion_factor = (1.0/(self.slope/1000)) if self.slope != 0 else None
            print(f"Factor de conversión: {conversion_factor}")
    
    def saveStatsToCSV(self, filename):
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Tiempo (s)', 'Posicion Z Corregida (nm)'])
            writer.writerows(self.stats)
        print(f"Datos guardados en {filename}")
        
    def resetStdCalculation(self):
        self.stdData = []
        self.calculating_std = True
        self.startTime = time.time()
    
    def startStdCalculation(self):
        self.stdData = []
        self.calculating_std = True
        self.startTime = time.time()

    def stopMeasurement(self):
        self.measuring = False
        if len(self.z_positions) > 1:
            std_dev = np.std(self.z_positions)
            print(f"Desvío estándar de la posición Z: {std_dev} nm")
            return std_dev
        else:
            print("No se recogieron suficientes datos para calcular el desvío estándar.")
            return None

def main():
    path_to_dll = r'C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll'
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    
    dark_stylesheet = """
        QWidget { 
            background-color: #2b2b2b; 
            color: #f0f0f0; 
            font-family: 'Segoe UI', Arial;
        }
        QMainWindow { 
            background-color: #2b2b2b; 
        }
        QGroupBox {
            font-size: 13px; 
            font-weight: bold;
            border: 2px solid #555555; 
            border-radius: 6px; 
            margin-top: 12px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; 
            subcontrol-position: top left;
            padding: 2px 8px; 
            margin-left: 8px;
            background-color: #2b2b2b;
        }
        QPushButton { 
            background-color: #3d3d3d; 
            border: 1px solid #555555; 
            padding: 6px 12px; 
            border-radius: 4px;
            font-size: 12px;
        }
        QPushButton:hover { 
            background-color: #4a4a4a; 
            border: 1px solid #666666;
        }
        QPushButton:pressed { 
            background-color: #2a2a2a; 
        }
        QLineEdit { 
            background-color: #1e1e1e; 
            padding: 5px; 
            border: 1px solid #555555; 
            border-radius: 3px;
        }
        QCheckBox {
            spacing: 5px;
        }
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 3px;
            border: 1px solid #555555;
            background-color: #1e1e1e;
        }
        QCheckBox::indicator:checked {
            background-color: #0d7377;
            border: 1px solid #0d7377;
        }
        QLabel {
            padding: 2px;
        }
    """
    app.setStyleSheet(dark_stylesheet)
    
    ex = FocusGUI()
    ex.madpiezo = Madpiezo(path_to_dll)
    ex.focusWorker = focusWorker(ex, ex.madpiezo)  
    ex.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()