# Dropbox Install

Tool to package and upload iPhone AdHoc builds to Dropbox to allow over-the-air installation on iPhones and iPads.

## Dropbox-Uploader

This project requires the use of a modified version of the Dropbox-Uploader, available here: (https://github.com/zzymyn/Dropbox-Uploader). This tool should be set up before using the DropboxInstall tool.

## Usage

1. Set up Dropbox-Uploader by running externals/Dropbox-Uploader/dropbox_uploader.sh and following the instructions.
2. Build a "distrubution" build of your app in XCode. This can either be a Archive build or a regular build. You must sign with an "iPhone Distribution" code signing identity. This process should be the same as any other AdHoc build.
3. Run DropboxInstallpy on the built .app bundle.
4. After the script is complete, you will be given a link to a html page that can be viewed on an iOS device to start the OTA install.
