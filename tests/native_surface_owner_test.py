#!/usr/bin/env python3
"""Hidden native SurfaceView owners must not remain composited by Cocoa."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''package fixture;
import android.view.*;import java.lang.ref.WeakReference;
public class OwnerContract{
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static void set(Class<?> c,Object object,String name,Object value)throws Exception{var f=c.getDeclaredField(name);f.setAccessible(true);f.set(object,value);}
 public static void main(String[]args)throws Exception{
  var uf=sun.misc.Unsafe.class.getDeclaredField("theUnsafe");uf.setAccessible(true);var unsafe=(sun.misc.Unsafe)uf.get(null);
  SurfaceView owner=(SurfaceView)unsafe.allocateInstance(SurfaceView.class);
  set(SurfaceView.class,null,"sNativeWindowOwner",new WeakReference<>(owner));set(SurfaceView.class,null,"sHadNativeWindowOwner",true);
  set(View.class,owner,"macapkAttached",true);set(View.class,owner,"visibility",View.VISIBLE);
  check(SurfaceView.macapkNativeWindowLayerZ()==1,"visible owner not below its window");
  set(View.class,owner,"visibility",View.GONE);check(SurfaceView.macapkNativeWindowLayerZ()==-1,"GONE camera owner still published");
  set(View.class,owner,"visibility",View.INVISIBLE);check(SurfaceView.macapkNativeWindowLayerZ()==-1,"invisible owner still published");
  set(View.class,owner,"visibility",View.VISIBLE);set(View.class,owner,"macapkAttached",false);check(SurfaceView.macapkNativeWindowLayerZ()==-1,"detached owner still published");
  set(View.class,owner,"macapkAttached",true);check(SurfaceView.macapkNativeWindowLayerZ()==1,"visible owner did not recover");
  android.widget.FrameLayout ancestor=(android.widget.FrameLayout)unsafe.allocateInstance(android.widget.FrameLayout.class);set(View.class,ancestor,"visibility",View.GONE);set(View.class,ancestor,"macapkAttached",true);set(View.class,owner,"parent",ancestor);
  check(SurfaceView.macapkNativeWindowLayerZ()==-1,"hidden ancestor still published owner");set(View.class,owner,"parent",null);
  owner.setZOrderOnTop(true);check(SurfaceView.macapkNativeWindowLayerZ()==2,"on-top order changed");
  set(SurfaceView.class,null,"sNativeWindowOwner",null);check(SurfaceView.macapkNativeWindowLayerZ()==1,"previous-owner legacy order changed");
  set(SurfaceView.class,null,"sHadNativeWindowOwner",false);check(SurfaceView.macapkNativeWindowLayerZ()==0,"ownerless Unity path changed");
  System.out.println("PASS real owner visibility policy: hidden, detached, visible recovery and legacy order");
 }
}'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--jdk-home", type=Path, required=True)
    p.add_argument("--work-root", type=Path, required=True)
    p.add_argument("--source-overlay", action="store_true")
    a = p.parse_args(); a.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-owner-", dir=a.work_root) as temporary:
        root=Path(temporary);java=root/"OwnerContract.java";java.write_text(JAVA)
        cp=os.pathsep.join(str(a.source/"runtime/build/lib"/n)for n in("android-framework.jar","macapk-loader.jar"))
        files=[str(java)]
        if a.source_overlay: files.append(str(a.source/"runtime/java/android/view/SurfaceView.java"))
        subprocess.run([str(a.jdk_home/"bin/javac"),"-cp",cp,"-d",str(root),*files],check=True,timeout=30)
        subprocess.run([str(a.jdk_home/"bin/java"),"-cp",str(root)+os.pathsep+cp,"fixture.OwnerContract"],check=True,timeout=10)
        cocoa=(a.source/"runtime/src/cocoa_bridge.mm").read_text()
        begin=cocoa.index("// >>> SVGUESTZ-GATE-BEGIN")
        end=cocoa.index("// <<< SVGUESTZ-GATE-END",begin)
        policy=cocoa[begin:end]
        cpp=root/"policy.cpp";cpp.write_text("#include <cassert>\n"+policy+r'''
int main(){assert(!macapk_guest_layer_owner_visible(-1));assert(macapk_guest_layer_owner_visible(0));assert(macapk_guest_layer_owner_visible(1));assert(macapk_guest_layer_owner_visible(2));
 assert(macapk_guest_layer_z_for(1,0.5)==0.2);assert(macapk_guest_layer_z_for(2,0.5)==0.6);}
''')
        subprocess.run(["clang++","-std=c++17",str(cpp),"-o",str(root/"policy")],check=True,timeout=20)
        subprocess.run([str(root/"policy")],check=True,timeout=5)
        for name in ("macapk_sv_layer_show_on_main", "macapk_reassert_native_egl_layer", "MacapkSyncGuestLayerZ"):
            start=cocoa.index("static void "+name+"(");finish=cocoa.index("\n}",start)
            assert "macapk_guest_layer_owner_visible" in cocoa[start:finish], name+" ignores hidden owner"
        print("PASS native hide/show policy covers publication, redraw and guard timer without focus calls")


if __name__=="__main__":main()
