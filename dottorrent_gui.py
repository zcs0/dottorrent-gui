#!/usr/bin/env python3

from datetime import datetime
import os
import sys
import traceback

from PyQt5 import QtCore, QtGui, QtWidgets
import dottorrent
import humanfriendly

from ui_mainwindow import Ui_MainWindow
from ui_about import Ui_AboutDialog
from version import __version__


PROGRAM_NAME = "dottorrent-gui {}".format(__version__)
CREATOR = "dottorrent-gui/{} dottorrent/{}".format(
    __version__, dottorrent.__version__)

PIECE_SIZES = [2 ** i for i in range(14, 23)]


def _isChecked(checkbox):
    return checkbox.checkState() == QtCore.Qt.Checked


class CreateTorrentQThread(QtCore.QThread):

    progress_update = QtCore.pyqtSignal(str, int, int)

    def __init__(self, torrent, save_path):
        super().__init__()
        self.torrent = torrent
        self.save_path = save_path

    def run(self):
        def progress_callback(*args):
            self.progress_update.emit(*args)
            return self.isInterruptionRequested()

        self.torrent.creation_date = datetime.now()
        self.torrent.created_by = CREATOR
        self.success = self.torrent.generate(callback=progress_callback)
        if self.success:
            with open(self.save_path, 'wb') as f:
                self.torrent.save(f)


class CreateTorrentBatchQThread(QtCore.QThread):

    progress_update = QtCore.pyqtSignal(str, int, int)

    def __init__(self, path, save_dir, trackers, web_seeds,
                 private, comment, include_md5):
        super().__init__()
        self.path = path
        self.save_dir = save_dir
        self.trackers = trackers
        self.web_seeds = web_seeds
        self.private = private
        self.comment = comment
        self.include_md5 = include_md5

    def run(self):
        def callback(*args):
            return self.isInterruptionRequested()

        entries = os.listdir(self.path)
        for i, p in enumerate(entries):
            p = os.path.join(self.path, p)
            sfn = os.path.split(p)[1] + '.torrent'
            self.progress_update.emit(sfn, i, len(entries))
            t = dottorrent.Torrent(
                p,
                trackers=self.trackers,
                web_seeds=self.web_seeds,
                private=self.private,
                comment=self.comment,
                include_md5=self.include_md5,
                creation_date=datetime.now(),
                created_by=CREATOR)
            self.success = t.generate(callback=callback)
            if self.isInterruptionRequested():
                return
            with open(os.path.join(self.save_dir, sfn), 'wb') as f:
                t.save(f)


class DottorrentGUI(Ui_MainWindow):

    def setupUi(self, MainWindow):
        super().setupUi(MainWindow)
        MainWindow.setWindowTitle(PROGRAM_NAME)

        self.torrent = None
        self.MainWindow = MainWindow

        self.actionAbout.triggered.connect(self.showAboutDialog)

        self.fileRadioButton.toggled.connect(self.inputTypeToggle)
        self.fileRadioButton.setChecked(True)
        self.directoryRadioButton.toggled.connect(self.inputTypeToggle)

        self.browseButton.clicked.connect(self.browseInput)
        self.batchModeCheckBox.stateChanged.connect(self.batchModeChanged)

        self.pieceCountLabel.hide()
        for x in PIECE_SIZES:
            self.pieceSizeComboBox.addItem(humanfriendly.format_size(x))

        self.pieceSizeComboBox.currentIndexChanged.connect(
            self.pieceSizeChanged)

        self.privateTorrentCheckBox.stateChanged.connect(
            self.privateTorrentChanged)

        self.md5CheckBox.stateChanged.connect(
            self.md5Changed)

        self.progressBar.hide()
        self.createButton.setEnabled(False)
        self.createButton.clicked.connect(self.createButtonClicked)
        self.cancelButton.hide()
        self.cancelButton.clicked.connect(self.cancel_creation)
        self.resetButton.clicked.connect(lambda: self.setupUi(MainWindow))

    def _statusBarMsg(self, msg):
        self.MainWindow.statusBar().showMessage(msg)

    def showAboutDialog(self):
        qdlg = QtWidgets.QDialog()
        ad = Ui_AboutDialog()
        ad.setupUi(qdlg)
        ad.programVersionLabel.setText("version {}".format(__version__))
        ad.dtVersionLabel.setText("(dottorrent {})".format(
            dottorrent.__version__))
        qdlg.exec_()

    def inputTypeToggle(self):
        if self.fileRadioButton.isChecked():
            self.inputType = 'file'
            self.batchModeCheckBox.setCheckState(QtCore.Qt.Unchecked)
            self.batchModeCheckBox.setEnabled(False)
            self.batchModeCheckBox.hide()
        else:
            self.inputType = 'directory'
            self.batchModeCheckBox.setEnabled(True)
            self.batchModeCheckBox.show()
        self.inputEdit.setText('')

    def browseInput(self):
        if self.inputType == 'file':
            fn = QtWidgets.QFileDialog.getOpenFileName(
                self.MainWindow, 'Select file')
            if fn[0]:
                self.inputEdit.setText(fn[0])
        else:
            dn = QtWidgets.QFileDialog.getExistingDirectory(
                self.MainWindow, 'Select directory')
            if dn:
                self.inputEdit.setText(dn)
        self.initializeTorrent()

    def batchModeChanged(self, state):
        if state == QtCore.Qt.Checked:
            self.pieceSizeLabel.hide()
            self.pieceSizeComboBox.hide()
            self.pieceCountLabel.hide()
        else:
            self.pieceSizeLabel.show()
            self.pieceSizeComboBox.show()
            self.pieceCountLabel.show()

    def initializeTorrent(self):
        self.torrent = dottorrent.Torrent(
            self.inputEdit.text(),
            private=_isChecked(self.privateTorrentCheckBox),
            comment=self.commentEdit.text())
        try:
            t_info = self.torrent.get_info()
        except Exception as e:
            self.torrent = None
            errdlg = QtWidgets.QErrorMessage()
            errdlg.showMessage(str(e))
            errdlg.exec_()
            traceback.print_exc()
            return
        ptail = os.path.split(self.torrent.path)[1]
        if self.inputType == 'file':
            self._statusBarMsg(
                "{}: {}".format(ptail, humanfriendly.format_size(t_info[0])))
        else:
            self._statusBarMsg(
                "{}: {} files, {}".format(
                    ptail, t_info[1], humanfriendly.format_size(t_info[0])))
        self.pieceSizeComboBox.setCurrentIndex(PIECE_SIZES.index(t_info[2]))
        self.updatePieceCountLabel(t_info[3])
        self.pieceCountLabel.show()
        self.createButton.setEnabled(True)

    def commentEdited(self, comment):
        if getattr(self, 'torrent', None):
            self.torrent.comment = comment

    def pieceSizeChanged(self, index):
        if getattr(self, 'torrent', None):
            self.torrent.piece_size = PIECE_SIZES[index]
            t_info = self.torrent.get_info()
            self.updatePieceCountLabel(t_info[3])

    def updatePieceCountLabel(self, pc):
        self.pieceCountLabel.setText("{} pieces".format(pc))

    def privateTorrentChanged(self, state):
        if getattr(self, 'torrent', None):
            self.torrent.private = (state == QtCore.Qt.Checked)

    def md5Changed(self, state):
        if getattr(self, 'torrent', None):
            self.torrent.include_md5 = (state == QtCore.Qt.Checked)

    def createButtonClicked(self):
        # Validate trackers and web seed URLs
        trackers = self.trackerEdit.toPlainText().strip().split()
        web_seeds = self.webSeedEdit.toPlainText().strip().split()
        try:
            self.torrent.trackers = trackers
            self.torrent.web_seeds = web_seeds
        except Exception as e:
            errdlg = QtWidgets.QErrorMessage()
            errdlg.showMessage(str(e))
            errdlg.exec_()
            return
        if _isChecked(self.batchModeCheckBox):
            self.createTorrentBatch()
        else:
            self.createTorrent()

    def createTorrent(self):
        save_fn = os.path.splitext(
            os.path.split(self.inputEdit.text())[1])[0] + '.torrent'
        fn = QtWidgets.QFileDialog.getSaveFileName(
            self.MainWindow, 'Save torrent', save_fn,
            filter=('Torrent file (*.torrent)'))
        if fn[0]:
            self.creation_thread = CreateTorrentQThread(
                self.torrent,
                fn[0])
            self.creation_thread.started.connect(
                self.creation_started)
            self.creation_thread.progress_update.connect(
                self._progress_update)
            self.creation_thread.finished.connect(
                self.creation_finished)
            self.creation_thread.start()

    def createTorrentBatch(self):
        save_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.MainWindow, 'Select output directory')
        if save_dir:
            trackers = self.trackerEdit.toPlainText().strip().split()
            web_seeds = self.webSeedEdit.toPlainText().strip().split()
            self.creation_thread = CreateTorrentBatchQThread(
                path=self.inputEdit.text(),
                save_dir=save_dir,
                trackers=trackers,
                web_seeds=web_seeds,
                private=_isChecked(self.privateTorrentCheckBox),
                comment=self.commentEdit.text(),
                include_md5=_isChecked(self.md5CheckBox)
            )
            self.creation_thread.started.connect(
                self.creation_started)
            self.creation_thread.progress_update.connect(
                self._progress_update_batch)
            self.creation_thread.finished.connect(
                self.creation_finished)
            self.creation_thread.start()

    def cancel_creation(self):
        self.creation_thread.requestInterruption()

    def _progress_update(self, fn, pc, pt):
        fn = os.path.split(fn)[1]
        msg = "{} ({}/{})".format(fn, pc, pt)
        self.updateProgress(msg, int(round(100 * pc / pt)))

    def _progress_update_batch(self, fn, tc, tt):
        msg = "({}/{}) {}".format(tc, tt, fn)
        self.updateProgress(msg, int(round(100 * tc / tt)))

    def updateProgress(self, statusMsg, pv):
        self._statusBarMsg(statusMsg)
        self.progressBar.setValue(pv)

    def creation_started(self):
        self.inputGroupBox.setEnabled(False)
        self.seedingGroupBox.setEnabled(False)
        self.optionGroupBox.setEnabled(False)
        self.progressBar.show()
        self.createButton.hide()
        self.cancelButton.show()
        self.resetButton.setEnabled(False)

    def creation_finished(self):
        self.inputGroupBox.setEnabled(True)
        self.seedingGroupBox.setEnabled(True)
        self.optionGroupBox.setEnabled(True)
        self.progressBar.hide()
        self.createButton.show()
        self.cancelButton.hide()
        self.resetButton.setEnabled(True)
        if self.creation_thread.success:
            self._statusBarMsg('Finished')
        else:
            self._statusBarMsg('Canceled')
        self.creation_thread = None

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = DottorrentGUI()
    ui.setupUi(MainWindow)
    MainWindow.show()
    sys.exit(app.exec_())
