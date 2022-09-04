# coding=utf-8
from UM.Application import Application
from UM.OutputDevice.OutputDevice import OutputDevice
from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin
from UM.Logger import Logger
from UM.OutputDevice import OutputDeviceError
from cura.Snapshot import Snapshot
from cura.CuraApplication import CuraApplication

from PyQt6.QtWidgets import QFileDialog
from UM.Message import Message
from PyQt6.QtCore import QUrl,Qt
from PyQt6.QtGui import QDesktopServices

import sys
import os

import base64

from UM.i18n import i18nCatalog
catalog = i18nCatalog("uranium")

class CrealityThumbnail(OutputDevicePlugin): #We need to be an OutputDevicePlugin for the plug-in system.
    ##  Called upon launch.
    #
    #   You can use this to make a connection to the device or service, and
    #   register the output device to be displayed to the user.
    def start(self):
        self.getOutputDeviceManager().addOutputDevice(Save_File()) #Since this class is also an output device, we can just register ourselves.
        #You could also add more than one output devices here.
        #For instance, you could listen to incoming connections and add an output device when a new device is discovered on the LAN.

    ##  Called upon closing.
    #
    #   You can use this to break the connection with the device or service, and
    #   you should unregister the output device to be displayed to the user.
    def stop(self):
        self.getOutputDeviceManager().removeOutputDevice("Creality_store_gcode") #Remove all devices that were added. In this case it's only one.

class Save_File(OutputDevice):
    def __init__(self):
        super().__init__("save_with_screenshot")
        self.setName("save_with_screenshot")
        self.setPriority(2)
        self._preferences = Application.getInstance().getPreferences()
        name1 = "Save as Creality format"
        if CuraApplication.getInstance().getPreferences().getValue("general/language") == "zh_CN":
            name1 = "以创想三维格式保存"
        else:
            name1 = "Save as Creality format"
        self.setShortDescription(catalog.i18nc("@action:button", name1))
        self.setDescription(catalog.i18nc("@properties:tooltip", name1))
        self.setIconName("save")
        self._writing = False

    def requestWrite(self, nodes, file_name=None, limit_mimetypes=None, file_handler=None, **kwargs):
        if self._writing:
            raise OutputDeviceError.DeviceBusyError()

            # Set up and display file dialog
        dialog = QFileDialog()

        dialog.setWindowTitle(catalog.i18nc("@title:window", "Save to File"))
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)

        # Ensure platform never ask for overwrite confirmation since we do this ourselves
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite)

        if sys.platform == "linux" and "KDE_FULL_SESSION" in os.environ:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog)

        filters = []
        mime_types = []
        selected_filter = None
        last_used_type = self._preferences.getValue("local_file/last_used_type")

        if not file_handler:
            file_handler = Application.getInstance().getMeshFileHandler()

        file_types = file_handler.getSupportedFileTypesWrite()

        file_types.sort(key=lambda k: k["description"])
        if limit_mimetypes:
            file_types = list(filter(lambda i: i["mime_type"] in limit_mimetypes, file_types))

        if len(file_types) == 0:
            Logger.log("e", "There are no file types available to write with!")
            raise OutputDeviceError.WriteRequestFailedError()

        for item in file_types:
            type_filter = "{0} (*.{1})".format(item["description"], item["extension"])
            filters.append(type_filter)
            mime_types.append(item["mime_type"])
            if last_used_type == item["mime_type"]:
                selected_filter = type_filter
                if file_name:
                    file_name += "." + item["extension"]

        dialog.setNameFilters(filters)
        if selected_filter is not None:
            dialog.selectNameFilter(selected_filter)

        if file_name is not None:
            dialog.selectFile(file_name)

        stored_directory = self._preferences.getValue("local_file/dialog_save_path")
        dialog.setDirectory(stored_directory)

        if not dialog.exec():
            raise OutputDeviceError.UserCanceledError()

        save_path = dialog.directory().absolutePath()
        self._preferences.setValue("local_file/dialog_save_path", save_path)

        selected_type = file_types[filters.index(dialog.selectedNameFilter())]
        self._preferences.setValue("local_file/last_used_type", selected_type["mime_type"])

        # Get file name from file dialog
        file_name = dialog.selectedFiles()[0]
        active_build_plate = Application.getInstance().getMultiBuildPlateModel().activeBuildPlate
        scene = Application.getInstance().getController().getScene()
        gcode_dict = getattr(scene, "gcode_dict", None)
        if not gcode_dict:
            return
        _gcode = gcode_dict.get(active_build_plate, None)
        self.save_gcode(file_name, _gcode)

    def save_gcode(self, file_name, _gcode):
        global_container_stack = Application.getInstance().getGlobalContainerStack()
        if not global_container_stack:
            return
        job_name = Application.getInstance().getPrintInformation().jobName.strip()
        if job_name is "":
            job_name = "untitled_print"
        job_name = "%s.gcode" % job_name
        # Logger.log("d", os.path.abspath("")+"\\test.png")
        message = Message(catalog.i18nc("@info:status", "Saving to <filename>{0}</filename>").format(file_name),
                          0, False, -1)
        try:
            message.show()
            save_file = open(file_name, "w")
            if True:
                try:
                    ssnapshot = Snapshot.snapshot(48, 48)
                    bsnapshot = Snapshot.snapshot(200, 200)
                except Exception:
                    Logger.logException("w", "Failed to create snapshot image")
                save_file.write(self.add_screenshot(ssnapshot, 48, 48, 'jpg'))
                save_file.write('\n')
                save_file.write(self.add_screenshot(bsnapshot, 200, 200, 'jpg'))
                save_file.write("\n")
            for line in _gcode:
                save_file.write(line)
            save_file.close()
            message.hide()
            self.writeFinished.emit(self)
            self.writeSuccess.emit(self)
            message = Message(
                catalog.i18nc("@info:status", "Saved to <filename>{0}</filename>").format(file_name))
            message.addAction("open_folder", catalog.i18nc("@action:button", "Open Folder"), "open-folder",
                              catalog.i18nc("@info:tooltip", "Open the folder containing the file"))
            message._folder = os.path.dirname(file_name)
            message.actionTriggered.connect(self._onMessageActionTriggered)
            message.show()
        except Exception as e:
            message.hide()
            message = Message(catalog.i18nc("@info:status",
                                            "Could not save to <filename>{0}</filename>: <message>{1}</message>").format(
                file_name, str(e)), lifetime=0)
            message.show()
            self.writeError.emit(self)

    def _onMessageActionTriggered(self, message, action):
        if action == "open_folder" and hasattr(message, "_folder"):
            QDesktopServices.openUrl(QUrl.fromLocalFile(message._folder))

    def add_screenshot(self, img, width, height, img_type):
        currentPath = self._preferences.getValue("local_file/dialog_profile_path")+"\\preview.jpg"
        img.save(currentPath)
        result = ""
        try:
            image = open(currentPath,'rb')
            if True:
                image_read = image.read()
                image.close()

                image_64_encode = base64.b64encode(image_read)

                icount = len(image_64_encode)
                lineNum=0
                if icount%76==0:
                    lineNum = icount/76
                else:
                    lineNum = icount / 76 +1
                lineNum += 2 # 头尾两行

                startLinNo = int(height* 0.0167 + 0.5)
                endLineNo = int(height-startLinNo)

                strhead =img_type+' begin '+str(width) +'*'+str(height) +' '+str(len(image_read))+' '+str(startLinNo)+' '+str(endLineNo)+' '+str(500)
                strend =img_type +' end'
                ilineNum =int(lineNum)
                for i in range(ilineNum):
                    if i == 0:
                        result += "; "
                        result += strhead
                        result += "\n"
                    elif i == ilineNum - 1:
                        result += "; "
                        result += strend
                        result += "\n"
                    elif i == ilineNum - 2:
                        #strHex = "%x" % str(image_64_encode[76*(i-1):])
                        result += "; "
                        result += str(image_64_encode[76*(i-1):],encoding = "utf-8")
                        result += "\n"
                    else:
                        #strHex = "%x" % str(image_64_encode[76*(i-1):76*(i-1)+76])
                        result += "; "
                        result += str(image_64_encode[76*(i-1):76*(i-1)+76],encoding = "utf-8")
                        result += "\n"
        except Exception:
            self.writeError.emit(self)
        return result
