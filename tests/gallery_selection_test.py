"""Filter cached synthetic gallery models before row/index construction."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

SOURCES = {
    "android/provider/MediaStoreProvider.java": """package android.provider; public final class MediaStoreProvider {
 public static java.util.Map<Integer,String> selected=java.util.Map.of(7,"/dev/fd/70",9,"/dev/fd/90");
 public static java.util.Map<Integer,String> macapkSelectedReferenceSnapshot(){return selected;}}
""",
    "com/instagram/common/gallery/Medium.java": """package com.instagram.common.gallery; public final class Medium {
 public int A06; public String A0e; public Medium(int id,String data){A06=id;A0e=data;}}
""",
    "com/instagram/common/gallery/model/GalleryItem.java": """package com.instagram.common.gallery.model; public class GalleryItem {
 public com.instagram.common.gallery.Medium A02; public GalleryItem(com.instagram.common.gallery.Medium m){A02=m;}
 public static final class CameraCaptureMedium extends GalleryItem{public CameraCaptureMedium(){super(null);}}
 public static final class LocalGalleryMedium extends GalleryItem{public final com.instagram.common.gallery.Medium A00;public LocalGalleryMedium(com.instagram.common.gallery.Medium m){super(m);A00=m;}}}
""",
    "X/D5A.java": """package X; public final class D5A {
 public final java.util.List A0T,A0U,A0V,A0W,A0X,A0Y;
 public D5A(java.util.List source){A0T=source;A0U=source;A0V=source;A0W=source;A0X=source;A0Y=source;}}
""",
    "GallerySelectionContract.java": """import java.util.*; import com.instagram.common.gallery.*;import com.instagram.common.gallery.model.*;
 public class GallerySelectionContract{public static void main(String[]args)throws Exception{
 var browse=new GalleryItem.CameraCaptureMedium();var chosen=new GalleryItem.LocalGalleryMedium(new Medium(7,"/dev/fd/70"));
 var otherChosen=new GalleryItem.LocalGalleryMedium(new Medium(9,"/dev/fd/90"));
 var legacy=new GalleryItem.LocalGalleryMedium(new Medium(2,"/synthetic/unselected"));
 var stale=new GalleryItem.LocalGalleryMedium(new Medium(7,"/dev/fd/71"));var remote=new GalleryItem(null);
 var source=new ArrayList<>(List.of(browse,legacy,chosen,remote,stale,otherChosen));var model=new X.D5A(source);
 com.macapk.loader.InstagramGallerySelectionCompat.sanitizeModel(model);
 for(String name:new String[]{"A0T","A0U","A0V","A0W","A0X","A0Y"}){
  List filtered=(List)model.getClass().getField(name).get(model);
  if(filtered==source||filtered.size()!=3||filtered.get(0)!=browse||filtered.get(1)!=chosen||filtered.get(2)!=otherChosen)throw new AssertionError("cached model indices/content: "+name);
 }
 if(source.size()!=6||source.get(1)!=legacy)throw new AssertionError("shared cached source mutated");
 android.provider.MediaStoreProvider.selected=Map.of();com.macapk.loader.InstagramGallerySelectionCompat.sanitizeModel(model);
 if(model.A0U.size()!=1||model.A0U.get(0)!=browse||source.size()!=6)throw new AssertionError("unselected cached media leaked");
 System.out.println("PASS selected gallery: legacy/remote/stale references excluded; selected order and Browse kept; original cache lists untouched");}}
""",
    "VerifyGalleryRewrite.java": """import java.nio.file.*;import java.util.*;import java.util.jar.*;
public final class VerifyGalleryRewrite {
 static final class Loader extends ClassLoader{Loader(){super(VerifyGalleryRewrite.class.getClassLoader());}Class<?> link(byte[]b){Class<?>c=defineClass("X.D5A",b,0,b.length);resolveClass(c);return c;}}
 public static void main(String[]args)throws Exception{
  byte[]raw;try(var jar=new JarFile(args[0])){raw=jar.getInputStream(jar.getJarEntry("X/D5A.class")).readAllBytes();}
  var result=com.macapk.loader.ClassFileRewriter.maybeRewrite(raw,"X.D5A");if(!result.rewritten)throw new AssertionError("tested gallery class not rewritten");
  Class<?> actual=new Loader().link(result.bytes);actual.getDeclaredMethod("A0A");
  byte[]other=raw.clone();other[other.length-1]^=1;
  if(com.macapk.loader.ClassFileRewriter.maybeRewrite(other,"X.D5A").rewritten)throw new AssertionError("unknown gallery class rewritten");
  System.out.println("PASS actual public gallery class: fingerprinted rewrite links/verifies; unknown fingerprint untouched");
 }}
""",
}


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, timeout=60, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--jdk-home", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--app-classes", type=Path, help="Optional public converted Instagram 445 class archive")
    options = parser.parse_args()
    options.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gallery-selection-", dir=options.work_root) as temporary:
        root = Path(temporary)
        for name, content in SOURCES.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        classpath = os.pathsep.join(str(options.source / "runtime/build/lib" / name) for name in ("android-framework.jar", "macapk-loader.jar"))
        fake_files = [root / name for name in SOURCES if name != "VerifyGalleryRewrite.java"]
        run([options.jdk_home / "bin/javac", "-cp", classpath, "-d", root / "synthetic",
             options.source / "runtime/java/com/macapk/loader/InstagramGallerySelectionCompat.java", *fake_files])
        run([options.jdk_home / "bin/java", "-cp", str(root / "synthetic") + os.pathsep + classpath, "GallerySelectionContract"])
        if options.app_classes:
            run([options.jdk_home / "bin/javac", "-cp", classpath, "-d", root / "actual",
                 options.source / "runtime/java/com/macapk/loader/ClassFileRewriter.java", root / "VerifyGalleryRewrite.java"])
            run([options.jdk_home / "bin/java", "-Xverify:all", "-cp", str(root / "actual") + os.pathsep + classpath + os.pathsep + str(options.app_classes),
                 "VerifyGalleryRewrite", options.app_classes], env=dict(os.environ, MACAPK_LOG_LEVEL="99"))


if __name__ == "__main__":
    main()
