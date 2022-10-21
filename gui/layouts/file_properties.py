# Form implementation generated from reading ui file '.\gui\layouts\file_properties.ui'
#
# Created by: PyQt6 UI code generator 6.4.0
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(300, 625)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.gridLayout = QtWidgets.QGridLayout()
        self.gridLayout.setObjectName("gridLayout")
        self.line_property_application = QtWidgets.QLineEdit(Dialog)
        self.line_property_application.setObjectName("line_property_application")
        self.gridLayout.addWidget(self.line_property_application, 2, 1, 1, 1)
        self.label_property_runtime = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_runtime.sizePolicy().hasHeightForWidth())
        self.label_property_runtime.setSizePolicy(sizePolicy)
        self.label_property_runtime.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_runtime.setObjectName("label_property_runtime")
        self.gridLayout.addWidget(self.label_property_runtime, 4, 0, 1, 1)
        self.label_property_capture_type = QtWidgets.QLabel(Dialog)
        self.label_property_capture_type.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_capture_type.sizePolicy().hasHeightForWidth())
        self.label_property_capture_type.setSizePolicy(sizePolicy)
        self.label_property_capture_type.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_capture_type.setObjectName("label_property_capture_type")
        self.gridLayout.addWidget(self.label_property_capture_type, 1, 0, 1, 1)
        self.label_property_application = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_application.sizePolicy().hasHeightForWidth())
        self.label_property_application.setSizePolicy(sizePolicy)
        self.label_property_application.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_application.setObjectName("label_property_application")
        self.gridLayout.addWidget(self.label_property_application, 2, 0, 1, 1)
        self.label_property_resolution = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_resolution.sizePolicy().hasHeightForWidth())
        self.label_property_resolution.setSizePolicy(sizePolicy)
        self.label_property_resolution.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_resolution.setObjectName("label_property_resolution")
        self.gridLayout.addWidget(self.label_property_resolution, 3, 0, 1, 1)
        self.line_property_capture_type = QtWidgets.QLineEdit(Dialog)
        self.line_property_capture_type.setReadOnly(True)
        self.line_property_capture_type.setObjectName("line_property_capture_type")
        self.gridLayout.addWidget(self.line_property_capture_type, 1, 1, 1, 1)
        self.line_property_resolution = QtWidgets.QLineEdit(Dialog)
        self.line_property_resolution.setObjectName("line_property_resolution")
        self.gridLayout.addWidget(self.line_property_resolution, 3, 1, 1, 1)
        self.line_property_gpu = QtWidgets.QLineEdit(Dialog)
        self.line_property_gpu.setObjectName("line_property_gpu")
        self.gridLayout.addWidget(self.line_property_gpu, 5, 1, 1, 1)
        self.line_property_runtime = QtWidgets.QLineEdit(Dialog)
        self.line_property_runtime.setObjectName("line_property_runtime")
        self.gridLayout.addWidget(self.line_property_runtime, 4, 1, 1, 1)
        self.label_property_gpu = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_gpu.sizePolicy().hasHeightForWidth())
        self.label_property_gpu.setSizePolicy(sizePolicy)
        self.label_property_gpu.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_gpu.setObjectName("label_property_gpu")
        self.gridLayout.addWidget(self.label_property_gpu, 5, 0, 1, 1)
        self.label_property_file_name = QtWidgets.QLabel(Dialog)
        self.label_property_file_name.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_file_name.sizePolicy().hasHeightForWidth())
        self.label_property_file_name.setSizePolicy(sizePolicy)
        self.label_property_file_name.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_file_name.setObjectName("label_property_file_name")
        self.gridLayout.addWidget(self.label_property_file_name, 7, 0, 1, 1)
        self.btn_reset_properties = QtWidgets.QPushButton(Dialog)
        self.btn_reset_properties.setAutoDefault(False)
        self.btn_reset_properties.setObjectName("btn_reset_properties")
        self.gridLayout.addWidget(self.btn_reset_properties, 9, 0, 1, 2)
        self.line_property_comments = QtWidgets.QLineEdit(Dialog)
        self.line_property_comments.setObjectName("line_property_comments")
        self.gridLayout.addWidget(self.line_property_comments, 6, 1, 1, 1)
        self.line_property_file_name = QtWidgets.QLineEdit(Dialog)
        self.line_property_file_name.setReadOnly(True)
        self.line_property_file_name.setObjectName("line_property_file_name")
        self.gridLayout.addWidget(self.line_property_file_name, 7, 1, 1, 1)
        self.label_property_comments = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_comments.sizePolicy().hasHeightForWidth())
        self.label_property_comments.setSizePolicy(sizePolicy)
        self.label_property_comments.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_comments.setObjectName("label_property_comments")
        self.gridLayout.addWidget(self.label_property_comments, 6, 0, 1, 1)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setSpacing(0)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.line_property_file_path = QtWidgets.QLineEdit(Dialog)
        self.line_property_file_path.setReadOnly(True)
        self.line_property_file_path.setObjectName("line_property_file_path")
        self.horizontalLayout_2.addWidget(self.line_property_file_path)
        self.btn_open_to_file = QtWidgets.QPushButton(Dialog)
        self.btn_open_to_file.setMaximumSize(QtCore.QSize(22, 22))
        self.btn_open_to_file.setAutoDefault(False)
        self.btn_open_to_file.setObjectName("btn_open_to_file")
        self.horizontalLayout_2.addWidget(self.btn_open_to_file)
        self.gridLayout.addLayout(self.horizontalLayout_2, 8, 1, 1, 1)
        self.label_property_file_path = QtWidgets.QLabel(Dialog)
        self.label_property_file_path.setEnabled(False)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_property_file_path.sizePolicy().hasHeightForWidth())
        self.label_property_file_path.setSizePolicy(sizePolicy)
        self.label_property_file_path.setMinimumSize(QtCore.QSize(70, 0))
        self.label_property_file_path.setObjectName("label_property_file_path")
        self.gridLayout.addWidget(self.label_property_file_path, 8, 0, 1, 1)
        self.info_label_property_info = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.info_label_property_info.sizePolicy().hasHeightForWidth())
        self.info_label_property_info.setSizePolicy(sizePolicy)
        self.info_label_property_info.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.info_label_property_info.setWordWrap(True)
        self.info_label_property_info.setObjectName("info_label_property_info")
        self.gridLayout.addWidget(self.info_label_property_info, 0, 0, 1, 2)
        self.verticalLayout.addLayout(self.gridLayout)
        spacerItem = QtWidgets.QSpacerItem(0, 20, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)
        self.verticalLayout.addItem(spacerItem)
        self.gridLayout_2 = QtWidgets.QGridLayout()
        self.gridLayout_2.setObjectName("gridLayout_2")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.label = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy)
        self.label.setMinimumSize(QtCore.QSize(28, 0))
        self.label.setObjectName("label")
        self.horizontalLayout_3.addWidget(self.label)
        self.btn_pen_color = QtWidgets.QPushButton(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.btn_pen_color.sizePolicy().hasHeightForWidth())
        self.btn_pen_color.setSizePolicy(sizePolicy)
        self.btn_pen_color.setText("")
        self.btn_pen_color.setObjectName("btn_pen_color")
        self.horizontalLayout_3.addWidget(self.btn_pen_color)
        self.label_2 = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)
        self.label_2.setMinimumSize(QtCore.QSize(28, 0))
        self.label_2.setObjectName("label_2")
        self.horizontalLayout_3.addWidget(self.label_2)
        self.spin_pen_width = QtWidgets.QSpinBox(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.spin_pen_width.sizePolicy().hasHeightForWidth())
        self.spin_pen_width.setSizePolicy(sizePolicy)
        self.spin_pen_width.setMinimumSize(QtCore.QSize(50, 0))
        self.spin_pen_width.setMinimum(1)
        self.spin_pen_width.setMaximum(10)
        self.spin_pen_width.setObjectName("spin_pen_width")
        self.horizontalLayout_3.addWidget(self.spin_pen_width)
        self.gridLayout_2.addLayout(self.horizontalLayout_3, 0, 1, 1, 1)
        self.label_pen_color = QtWidgets.QLabel(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_pen_color.sizePolicy().hasHeightForWidth())
        self.label_pen_color.setSizePolicy(sizePolicy)
        self.label_pen_color.setMinimumSize(QtCore.QSize(70, 0))
        self.label_pen_color.setObjectName("label_pen_color")
        self.gridLayout_2.addWidget(self.label_pen_color, 0, 0, 1, 1)
        self.caution_label_pen_width = QtWidgets.QLabel(Dialog)
        self.caution_label_pen_width.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.caution_label_pen_width.setWordWrap(True)
        self.caution_label_pen_width.setObjectName("caution_label_pen_width")
        self.gridLayout_2.addWidget(self.caution_label_pen_width, 1, 0, 1, 2)
        self.verticalLayout.addLayout(self.gridLayout_2)
        spacerItem1 = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)
        self.verticalLayout.addItem(spacerItem1)
        self.gridLayout_3 = QtWidgets.QGridLayout()
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.info_label_legend_title = QtWidgets.QLabel(Dialog)
        self.info_label_legend_title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.info_label_legend_title.setWordWrap(True)
        self.info_label_legend_title.setObjectName("info_label_legend_title")
        self.gridLayout_3.addWidget(self.info_label_legend_title, 0, 0, 1, 2)
        self.line_custom_legend = QtWidgets.QLineEdit(Dialog)
        self.line_custom_legend.setClearButtonEnabled(True)
        self.line_custom_legend.setObjectName("line_custom_legend")
        self.gridLayout_3.addWidget(self.line_custom_legend, 1, 1, 1, 1)
        self.check_use_custom_legend = QtWidgets.QCheckBox(Dialog)
        self.check_use_custom_legend.setObjectName("check_use_custom_legend")
        self.gridLayout_3.addWidget(self.check_use_custom_legend, 1, 0, 1, 1)
        self.verticalLayout.addLayout(self.gridLayout_3)
        spacerItem2 = QtWidgets.QSpacerItem(20, 20, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding)
        self.verticalLayout.addItem(spacerItem2)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem3 = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self.horizontalLayout.addItem(spacerItem3)
        self.btn_ok = QtWidgets.QPushButton(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.btn_ok.sizePolicy().hasHeightForWidth())
        self.btn_ok.setSizePolicy(sizePolicy)
        self.btn_ok.setMinimumSize(QtCore.QSize(75, 0))
        self.btn_ok.setDefault(True)
        self.btn_ok.setObjectName("btn_ok")
        self.horizontalLayout.addWidget(self.btn_ok)
        self.btn_cancel = QtWidgets.QPushButton(Dialog)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.btn_cancel.sizePolicy().hasHeightForWidth())
        self.btn_cancel.setSizePolicy(sizePolicy)
        self.btn_cancel.setMinimumSize(QtCore.QSize(75, 0))
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.setObjectName("btn_cancel")
        self.horizontalLayout.addWidget(self.btn_cancel)
        self.verticalLayout.addLayout(self.horizontalLayout)

        self.retranslateUi(Dialog)
        self.btn_ok.clicked['bool'].connect(Dialog.accept) # type: ignore
        self.btn_cancel.clicked['bool'].connect(Dialog.reject) # type: ignore
        self.btn_open_to_file.clicked['bool'].connect(Dialog.open_file_location) # type: ignore
        self.btn_reset_properties.clicked['bool'].connect(Dialog.reset_file_properties) # type: ignore
        self.btn_pen_color.clicked['bool'].connect(Dialog.change_pen_color) # type: ignore
        QtCore.QMetaObject.connectSlotsByName(Dialog)
        Dialog.setTabOrder(self.line_property_capture_type, self.line_property_application)
        Dialog.setTabOrder(self.line_property_application, self.line_property_resolution)
        Dialog.setTabOrder(self.line_property_resolution, self.line_property_runtime)
        Dialog.setTabOrder(self.line_property_runtime, self.line_property_gpu)
        Dialog.setTabOrder(self.line_property_gpu, self.line_property_comments)
        Dialog.setTabOrder(self.line_property_comments, self.line_property_file_name)
        Dialog.setTabOrder(self.line_property_file_name, self.line_property_file_path)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "File Properties"))
        self.label_property_runtime.setText(_translate("Dialog", "Runtime"))
        self.label_property_capture_type.setText(_translate("Dialog", "Capture Type"))
        self.label_property_application.setText(_translate("Dialog", "Application"))
        self.label_property_resolution.setText(_translate("Dialog", "Resolution"))
        self.label_property_gpu.setText(_translate("Dialog", "GPU"))
        self.label_property_file_name.setText(_translate("Dialog", "File Name"))
        self.btn_reset_properties.setText(_translate("Dialog", "Reset Properties"))
        self.line_property_comments.setPlaceholderText(_translate("Dialog", "Raytracing, DLSS, overclock, etc."))
        self.label_property_comments.setText(_translate("Dialog", "Comments"))
        self.btn_open_to_file.setToolTip(_translate("Dialog", "Open a file explorer at this file\'s location."))
        self.btn_open_to_file.setText(_translate("Dialog", "..."))
        self.label_property_file_path.setText(_translate("Dialog", "File Path"))
        self.info_label_property_info.setText(_translate("Dialog", " Properties of plotted files can also be modified via the statistics table."))
        self.label.setText(_translate("Dialog", "Color"))
        self.label_2.setText(_translate("Dialog", "Width"))
        self.spin_pen_width.setSuffix(_translate("Dialog", " px"))
        self.label_pen_color.setText(_translate("Dialog", "Plot Line"))
        self.caution_label_pen_width.setText(_translate("Dialog", "<html><head/><body><p><span style=\" font-weight:600;\">CAUTION!</span> Pen widths larger than 1 pixel can reduce responsiveness of panning and zooming. It is recommended to only adjust this value when you are ready to save your plots as images.</p></body></html>"))
        self.info_label_legend_title.setText(_translate("Dialog", "Enter text here to customize how this file appears in the plot legend. This can be helpful for distinguishing one file from the others, or when the desired format isn\'t compatible with Pydra\'s template system."))
        self.check_use_custom_legend.setText(_translate("Dialog", "Custom Legend"))
        self.btn_ok.setText(_translate("Dialog", "OK"))
        self.btn_cancel.setText(_translate("Dialog", "Cancel"))
