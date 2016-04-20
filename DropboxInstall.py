#!/usr/bin/env python

import sys
import os
import re
import glob
import argparse
import subprocess
import tempfile
import shutil

tmpDir = None

PLIST_BUDDY = "/usr/libexec/PlistBuddy"
MOBILE_PROVISIONS = "~/Library/MobileDevice/Provisioning Profiles/*.mobileprovision"
PACKAGE_APPLICATION = "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/usr/bin/PackageApplication"

def requireFile(path, errordesc, extraError = None):
    if not os.path.isfile(path):
        print("Error: " + errordesc + " not a file.")
        print("  path = " + path);
        if extraError is not None:
            print("       " + extraError)
        sys.exit(1)

def requireDir(path, errordesc, extraError = None):
    if not os.path.isdir(path):
        print("Error: " + errordesc + " not a directory.")
        print("  path = " + path);
        if extraError is not None:
            print("       " + extraError)
        sys.exit(1)

def requireMatch(pattern, string, errordesc):
    m = re.match(pattern, string)
    if m is None:
        print("Error: " + errordesc + " does not match expected pattern.")
        print("  value = " + string)
        print("  pattern = " + pattern)
        sys.exit(1)

def getPlistValue(path, key):
    return subprocess.check_output([PLIST_BUDDY, "-c", "Print " + key, path]).strip()

def writeMobileProvisionPList(mobileprovision, plistFile):
    with open(plistFile, "w") as f:
        r = subprocess.call(["security", "cms", "-D", "-i", mobileprovision], stdout = f)
    if r != 0:
        return False
    return True

def getMobileProvisionPlistValue(mobileprovision, key):
    tmpFile = os.path.join(tmpDir, "tmp.plist")
    if not writeMobileProvisionPList(mobileprovision, tmpFile):
        return None
    return getPlistValue(tmpFile, key)

def findSigningIdentity():
    output = subprocess.check_output(["security", "find-identity", "-v", "-p", "codesigning"])
    match = re.search(r"iPhone Distribution: .* \(.*\)", output)
    if match is None:
        print("Error: Failed to find signing identity.")
        sys.exit(1)
    return match.group(0)

def findMobileProvision(profileName):
    for mobileprovision in glob.iglob(os.path.expanduser(MOBILE_PROVISIONS)):
        name = getMobileProvisionPlistValue(mobileprovision, ":Name")
        if name == profileName:
            return mobileprovision
    print("Error: Failed to find mobile provision.")
    sys.exit(1)

def run(args):
    scriptDir = os.path.dirname(sys.argv[0])
    templateDir = os.path.join(scriptDir, "templates")
    binDir = os.path.join(scriptDir, "bin")

    dropboxUploaderScript = os.path.join(scriptDir, "externals", "Dropbox-Uploader", "dropbox_uploader.sh")
    dropboxUploaderScriptCheckFile = os.path.expanduser("~/.dropbox_uploader")

    bundlePath = args.bundle
    bundleInfoPlist = os.path.join(bundlePath, "Info.plist")
    bundleEmbeddedMobileProvision = os.path.join(bundlePath, "embedded.mobileprovision")

    packageApplication = os.path.join(tmpDir, "PackageApplication")
    packageApplicationPatch = os.path.join(scriptDir, "PackageApplication.patch")

    # package application needs absolute path:
    ipaTarget = os.path.realpath(os.path.join(tmpDir, "Output.ipa"))

    requireFile(dropboxUploaderScript, "Dropbox uploader script")
    requireFile(dropboxUploaderScriptCheckFile, "Dropbox uploader config file", "Please run: " + dropboxUploaderScript)
    requireDir(bundlePath, "Bundle")
    requireFile(bundleInfoPlist, "Bundle Info.plist")
    requireFile(bundleEmbeddedMobileProvision, "Bundle embedded.mobileprovision")

    print("Preparing...")

    print("  Creating our PackageApplication...")
    shutil.copy(PACKAGE_APPLICATION, packageApplication)
    subprocess.check_output(["patch", packageApplication, packageApplicationPatch])
    print("    " + packageApplication)

    print("    done")
    print("  done")

    print("Gathering Info...")

    bundleIdentifier = getPlistValue(bundleInfoPlist, ":CFBundleIdentifier")
    requireMatch(r"^\w+(\.\w+)*$", bundleIdentifier, "Bundle Identifier")
    print("  Bundle Identifier = " + bundleIdentifier)

    bundleVersion = getPlistValue(bundleInfoPlist, ":CFBundleVersion")
    requireMatch(r"^\d+(\.\d+)*$", bundleVersion, "Bundle Version")
    print("  Bundle Version = " + bundleVersion)

    bundleDisplayName = getPlistValue(bundleInfoPlist, ":CFBundleDisplayName")
    requireMatch(r"^.+$", bundleDisplayName, "Bundle Name")
    print("  Bundle Name = " + bundleDisplayName)

    ipaDropboxTarget = os.path.join(args.dropbox_root, bundleIdentifier, "Output.ipa")
    print("  Dropbox Target = " + ipaDropboxTarget)

    print("  done")

    print("Checking App...")

    if getMobileProvisionPlistValue(bundleEmbeddedMobileProvision, ":Entitlements:aps-environment") != "production":
        print("Error: Not a production environment app.")
        print("       Make sure you build with an 'iOS Distribution' code-signing identity")
        sys.exit(1)

    print("  done")

    print("Determining (re)signing info...")

    signingIdentity = findSigningIdentity()
    print("  Signing Identity = " + signingIdentity)

    mobileprovision = findMobileProvision("XC Ad Hoc: " + bundleIdentifier)
    print("  Mobile Provision = " + mobileprovision)

    print("Packaging application...")
    subprocess.check_call([packageApplication, bundlePath, "-s", signingIdentity, "-o", ipaTarget, "--embed", mobileprovision])
    print("  done")

    print("Uploading IPA to Dropbox...")
    subprocess.check_call([dropboxUploaderScript, "upload", ipaTarget, ipaDropboxTarget])
    print("  done")

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--dropbox-root", default = "/AdHoc Builds", help = "Path in DropBox to put builds.")
        parser.add_argument("bundle", help = "Path to .app bundle.")
        args = parser.parse_args()
        print(args)
        tmpDir = tempfile.mkdtemp()
        run(args)
    finally:
        shutil.rmtree(tmpDir)
