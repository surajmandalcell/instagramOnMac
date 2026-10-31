#!/usr/bin/env python3
"""Check built window-service classes, optionally with public app callbacks."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


POLICY = r'''
import android.os.*;
import android.view.IWindowManager;
public final class WindowServiceContract {
  public static void main(String[] args) throws Exception {
    IBinder binder = ServiceManager.getService("window");
    if (binder == null || binder != ServiceManager.getService("window")
        || binder != ServiceManager.checkService("window")) throw new AssertionError("stable window binder");
    IWindowManager service = IWindowManager.Stub.asInterface(binder);
    boolean expected = Boolean.parseBoolean(args[0]);
    if (service == null || service.asBinder() != binder || service.hasNavigationBar() != expected
        || service.hasNavigationBar(0) != expected) throw new AssertionError("window policy");
    if (!Boolean.valueOf(expected).equals(service.getClass().getMethod("hasNavigationBar").invoke(service)))
      throw new AssertionError("public reflective window policy");
    if (ServiceManager.getService("missing") != null || IWindowManager.Stub.asInterface(null) != null
        || IWindowManager.Stub.asInterface(new Binder()) != null) throw new AssertionError("unknown services stay absent");
    System.out.println("PASS stable local window binder; navigation=" + expected + "; unknown services absent");
  }
}
'''

ACTUAL = r'''
import android.app.*;
import android.content.res.*;
import android.graphics.Insets;
import android.util.DisplayMetrics;
import android.view.*;
public final class ActualClipsInsetsContract {
  public static void main(String[] args) throws Exception {
    android.os.Looper.prepareMainLooper();
    for (String name : new String[]{"sRealW", "sRealH"}) {
      var field = Class.forName("com.macapk.loader.DisplayConfig").getDeclaredField(name);
      field.setAccessible(true); field.setInt(null, name.equals("sRealW") ? 636 : 1378);
    }
    DisplayMetrics metrics = new DisplayMetrics(); metrics.density = 2; metrics.densityDpi = 320;
    Resources resources = new Resources(new AssetManager(), metrics, Configuration.macapkPhoneDefaults());
    Activity activity = new Activity() {
      public Resources getResources() { return resources; }
      public Resources.Theme getTheme() { return resources.newTheme(); }
      public AssetManager getAssets() { return resources.getAssets(); }
      public String getPackageName() { return "window.fixture"; }
    };
    // Public Instagram 445 class names. No application or account is started.
    Class<?> manager = Class.forName("X.7nj");
    manager.getField("A0A").setBoolean(null, true);
    manager.getField("A0B").setBoolean(null, false);
    manager.getField("A07").setInt(null, -1);
    manager.getField("A08").setInt(null, -1);
    manager.getField("A09").set(null, null);
    manager.getMethod("A03", Activity.class).invoke(null, activity);
    int[] calls = {0};
    manager.getMethod("A07", Activity.class, Runnable.class).invoke(null, activity, (Runnable)()->calls[0]++);
    if (calls[0] != 0) throw new AssertionError("setup must wait for insets");
    View root = activity.getWindow().getDecorView();
    WindowInsets insets = new WindowInsets.Builder().setSystemWindowInsets(Insets.of(0,24,0,0))
        .setStableInsets(Insets.of(0,24,0,0)).build();
    root.dispatchApplyWindowInsets(insets);
    if (calls[0] != 1) throw new AssertionError("actual Clips setup remains queued: " + calls[0]);
    root.dispatchApplyWindowInsets(insets);
    if (calls[0] != 1) throw new AssertionError("duplicate setup callback");
    System.out.println("PASS actual app insets callback releases Clips setup once");
  }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--jdk-home", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--app-classes", type=Path, help="Optional public Instagram 445 converted classes.jar")
    args = parser.parse_args()
    jars = [args.source / "runtime/build/lib" / name for name in ("android-framework.jar", "macapk-loader.jar")]
    required = jars + [args.jdk_home / "bin/javac", args.jdk_home / "bin/java"]
    if args.app_classes:
        required.append(args.app_classes)
    for path in required:
        if not path.is_file():
            parser.error(f"Required built artifact is absent: {path}")
    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="window-contract-", dir=args.work_root) as scratch:
        work = Path(scratch)
        sources = [("WindowServiceContract", POLICY)]
        if args.app_classes:
            sources.append(("ActualClipsInsetsContract", ACTUAL))
        java_files = []
        for name, code in sources:
            path = work / f"{name}.java"
            path.write_text(code, encoding="utf-8")
            java_files.append(str(path))
        classpath = os.pathsep.join(str(path.resolve()) for path in jars)
        if args.app_classes:
            classpath += os.pathsep + str(args.app_classes.resolve())
        subprocess.run([str(args.jdk_home / "bin/javac"), "-cp", classpath, "-d", str(work), *java_files], check=True, timeout=30)
        command = [str(args.jdk_home / "bin/java"), "-Djava.awt.headless=true", "-cp", str(work) + os.pathsep + classpath]
        env = dict(os.environ, MACAPK_SDK_INT="33", MACAPK_LOG_LEVEL="99")
        for enabled in (False, True):
            env["MACAPK_SYSTEM_BARS"] = "1" if enabled else "0"
            subprocess.run([*command, "WindowServiceContract", str(enabled).lower()], env=env, check=True, timeout=30)
        if args.app_classes:
            env["MACAPK_SYSTEM_BARS"] = "0"
            subprocess.run([*command, "ActualClipsInsetsContract"], env=env, check=True, timeout=30)


if __name__ == "__main__":
    main()
