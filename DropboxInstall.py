#!/usr/bin/env python

import sys
import os
import re
import string
import glob
import argparse
import subprocess
import tempfile
import shutil
import urllib

tmpDir = None

PLIST_BUDDY = "/usr/libexec/PlistBuddy"
MOBILE_PROVISIONS = "~/Library/MobileDevice/Provisioning Profiles/*.mobileprovision"
PACKAGE_APPLICATION = "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/usr/bin/PackageApplication"
OUTPUT_IPA = "Output.ipa"
ICON_PNG = "Icon.png"
MANIFEST_PLIST = "manifest.plist"
INDEX_HTML = "index.html"

def requireFile(path, errordesc, extraError = None):
    if not os.path.isfile(path):
        print "Error: " + errordesc + " not a file."
        print "  path = " + path
        if extraError is not None:
            print "       " + extraError
        sys.exit(1)

def requireDir(path, errordesc, extraError = None):
    if not os.path.isdir(path):
        print "Error: " + errordesc + " not a directory."
        print "  path = " + path
        if extraError is not None:
            print "       " + extraError
        sys.exit(1)

def requireMatch(pattern, string, errordesc):
    m = re.match(pattern, string)
    if m is None:
        print "Error: " + errordesc + " does not match expected pattern."
        print "  value = " + string
        print "  pattern = " + pattern
        sys.exit(1)

def getPlistValue(path, key):
    try:
        return subprocess.check_output([PLIST_BUDDY, "-c", "Print " + key, path]).strip()
    except:
        return ""

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

def findBestIcon(bundlePath, bundleInfoPlist):
    bestIcon = None
    bestSize = 0.0

    for key in [":CFBundleIcons:CFBundlePrimaryIcon:CFBundleIconFiles", ":CFBundleIcons~ipad:CFBundlePrimaryIcon:CFBundleIconFiles"]:
        for m in re.finditer(r"\w+(\d+(?:\.\d+)?)x\1", getPlistValue(bundleInfoPlist, key)):
            size = float(m.group(1))
            for scale, scaleSuffix in [(1, ""), (2, "@2x"), (3, "@3x")]:
                iconSize = size * scale
                if bestIcon is None or iconSize > bestSize:
                    for deviceSuffix in ["", "~iphone", "~ipad"]:
                        icon = os.path.join(bundlePath, m.group() + scaleSuffix + deviceSuffix + ".png")
                        if os.path.isfile(icon):
                            bestIcon = icon
                            bestSize = iconSize
    return bestIcon

def findSigningIdentity():
    output = subprocess.check_output(["security", "find-identity", "-v", "-p", "codesigning"])
    match = re.search(r"iPhone Distribution: .* \(.*\)", output)
    if match is None:
        print "Error: Failed to find signing identity."
        sys.exit(1)
    return match.group(0)

def findMobileProvision(profileName):
    for mobileprovision in glob.iglob(os.path.expanduser(MOBILE_PROVISIONS)):
        name = getMobileProvisionPlistValue(mobileprovision, ":Name")
        if name == profileName:
            return mobileprovision
    print "Error: Failed to find mobile provision."
    sys.exit(1)

class DropboxUploader:
    def __init__(self, uploaderDir):
        self.script = os.path.join(uploaderDir, "dropbox_uploader.sh")
        requireFile(self.script, "Dropbox uploader script")
        requireFile(os.path.expanduser("~/.dropbox_uploader"), "Dropbox uploader config file", "Please run: " + self.script)

    def upload(self, source, dest):
        subprocess.check_call([self.script, "upload", source, dest])

    def share(self, path):
        return subprocess.check_output([self.script, "share", path]).strip().replace("?dl=0", "").replace("www.dropbox.com", "dl.dropboxusercontent.com")

def run(args):
    scriptDir = os.path.dirname(sys.argv[0])
    templateDir = os.path.join(scriptDir, "templates")
    binDir = os.path.join(scriptDir, "bin")

    manifestTemplate = os.path.join(templateDir, MANIFEST_PLIST)
    manifestTarget = os.path.join(tmpDir, MANIFEST_PLIST)

    indexTemplate = os.path.join(templateDir, INDEX_HTML)
    indexTarget = os.path.join(tmpDir, INDEX_HTML)

    dropboxUploader = DropboxUploader(os.path.join(scriptDir, "externals", "Dropbox-Uploader"))

    bundlePath = args.bundle
    bundleInfoPlist = os.path.join(bundlePath, "Info.plist")
    bundleEmbeddedMobileProvision = os.path.join(bundlePath, "embedded.mobileprovision")

    packageApplication = os.path.join(tmpDir, "PackageApplication")
    packageApplicationPatch = os.path.join(scriptDir, "PackageApplication.patch")

    # package application needs absolute path:
    ipaTarget = os.path.realpath(os.path.join(tmpDir, OUTPUT_IPA))

    requireFile(manifestTemplate, "Manifest template")
    requireFile(indexTemplate, "Index template")
    requireDir(bundlePath, "Bundle")
    requireFile(bundleInfoPlist, "Bundle Info.plist")
    requireFile(bundleEmbeddedMobileProvision, "Bundle embedded.mobileprovision")

    print "Preparing..."

    print "  Creating our own PackageApplication..."
    shutil.copy(PACKAGE_APPLICATION, packageApplication)
    subprocess.check_output(["patch", packageApplication, packageApplicationPatch])
    print "    " + packageApplication

    print "    done"
    print "  done"

    print "Gathering Info..."

    bundleIdentifier = getPlistValue(bundleInfoPlist, ":CFBundleIdentifier")
    requireMatch(r"^\w+(\.\w+)*$", bundleIdentifier, "Bundle Identifier")
    bundleVersion = getPlistValue(bundleInfoPlist, ":CFBundleVersion")
    requireMatch(r"^\d+(\.\d+)*$", bundleVersion, "Bundle Version")
    bundleDisplayName = getPlistValue(bundleInfoPlist, ":CFBundleDisplayName")
    requireMatch(r"^.+$", bundleDisplayName, "Bundle Name")
    iconTarget = findBestIcon(bundlePath, bundleInfoPlist)

    dropboxRoot = os.path.join(args.dropbox_root, bundleIdentifier)
    ipaDropboxTarget = os.path.join(dropboxRoot, OUTPUT_IPA)
    iconDropboxTarget = os.path.join(dropboxRoot, ICON_PNG)
    manifestDropboxTarget = os.path.join(dropboxRoot, MANIFEST_PLIST)
    indexDropboxTarget = os.path.join(dropboxRoot, INDEX_HTML)

    print "  Bundle Identifier = " + bundleIdentifier
    print "  Bundle Version = " + bundleVersion
    print "  Bundle Name = " + bundleDisplayName

    print "  done"

    print "Checking App..."

    if getMobileProvisionPlistValue(bundleEmbeddedMobileProvision, ":Entitlements:aps-environment") != "production":
        print "Error: Not a production environment app."
        print "       Make sure you build with an 'iOS Distribution' code-signing identity"
        sys.exit(1)

    print "  done"

    print "Determining (re)signing info..."

    signingIdentity = findSigningIdentity()
    print "  Signing Identity = " + signingIdentity

    mobileprovision = findMobileProvision("XC Ad Hoc: " + bundleIdentifier)
    print "  Mobile Provision = " + mobileprovision

    print "Packaging application..."
    subprocess.check_call([packageApplication, bundlePath, "-s", signingIdentity, "-o", ipaTarget, "--embed", mobileprovision])
    print "  done"

    print "Uploading IPA to Dropbox..."
    dropboxUploader.upload(ipaTarget, ipaDropboxTarget)
    ipaDropboxUrl = dropboxUploader.share(ipaDropboxTarget)
    dropboxUploader.upload(iconTarget, iconDropboxTarget)
    iconDropboxUrl = dropboxUploader.share(iconDropboxTarget)
    print "  IPA URL = " + ipaDropboxUrl
    print "  done"

    print "Creating manifest..."
    with open(manifestTemplate, "r") as fIn:
        with open(manifestTarget, "w") as fOut:
            fOut.write(string.Template(fIn.read()).safe_substitute(
                IpaUrl = ipaDropboxUrl,
                BundleIdentifier = bundleIdentifier,
                BundleVersion = bundleVersion,
                Title = bundleDisplayName,
                IconUrl = iconDropboxUrl
                ))
    dropboxUploader.upload(manifestTarget, manifestDropboxTarget)
    manifestDropboxUrl = dropboxUploader.share(manifestDropboxTarget)
    print "  Manifest URL = " + manifestDropboxUrl
    print "  done"

    print "Creating index..."
    with open(indexTemplate, "r") as fIn:
        with open(indexTarget, "w") as fOut:
            fOut.write(string.Template(fIn.read()).safe_substitute(
                Title = bundleDisplayName,
                About = "",
                IconUrl = iconDropboxUrl,
                BundleVersion = bundleVersion,
                IpaSize = "%.1f MiB" % (os.path.getsize(ipaTarget) / 1048576.0),
                EscapedManifestUrl = urllib.quote(manifestDropboxUrl, safe = '')
                ))
    dropboxUploader.upload(indexTarget, indexDropboxTarget)
    indexDropboxUrl = dropboxUploader.share(indexDropboxTarget)
    print "  Index URL = " + indexDropboxUrl
    print "  done"

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--dropbox-root", default = "/AdHoc Builds", help = "Path in DropBox to put builds.")
        parser.add_argument("bundle", help = "Path to .app bundle.")
        args = parser.parse_args()
        print args
        tmpDir = tempfile.mkdtemp()
        run(args)
    finally:
        shutil.rmtree(tmpDir)
