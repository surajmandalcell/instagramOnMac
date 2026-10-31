#!/usr/bin/env python3
"""Real selected MOV cache, atomic output, reuse and AVPlayer frame contract."""
import sys
import argparse
import os
from pathlib import Path
import media_extractor_content_test as backend
import media_reference_test as references
APP_CLASSES = None
BUILT_REWRITER = False
BUILT_ONLY = False

backend.JAVA = r'''package com.macapk.loader;
import android.content.*;import android.content.pm.ProviderInfo;import android.content.res.Resources;
import android.provider.*;import java.nio.file.*;import java.util.*;
public class ContentExtractorContract {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 static void importedModel(String alias,java.io.File output)throws Exception{
  String jarPath=System.getProperty("macapk.test.appClasses");if(jarPath==null)return;
  Class<?> mediumClass=Class.forName("com.instagram.common.gallery.Medium");Object medium=mediumClass.getConstructor().newInstance();
  mediumClass.getField("A0e").set(medium,alias);mediumClass.getField("A0A").setInt(medium,3);mediumClass.getField("A04").setInt(medium,1000);
  byte[] raw;try(var jar=new java.util.jar.JarFile(jarPath);var in=jar.getInputStream(jar.getJarEntry("X/90w.class"))){raw=in.readAllBytes();}
  byte[] changed=ClassFileRewriter.maybeRewrite(raw,"X.90w").bytes;
  class Imported extends ClassLoader{Imported(){super(ContentExtractorContract.class.getClassLoader());}Class<?> define(){return defineClass("X.90w",changed,0,changed.length);}}
  Class<?> imported=new Imported().define(), provenance=Class.forName("com.instagram.unifieddatamodel.video.ProvenanceMetadata");
  Object metadata=provenance.getConstructors()[0].newInstance(new Object[]{null,null,null,null,null,null,null});
  Object model=imported.getConstructor(mediumClass,provenance,int.class,int.class,int.class).newInstance(medium,metadata,64,48,0);
  String path=(String)imported.getField("A0n").get(model);
  check(path.equals(output.getAbsolutePath())&&path.endsWith(".mp4")&&new java.io.File(path).isFile(),"actual import model did not use regular cached MP4");
  check(imported.getField("A0Q").get(model)==medium&&mediumClass.getField("A0A").getInt(medium)==3,"import lost original selected video model");
  check(alias.equals(mediumClass.getField("A0e").get(medium)),"import changed original Medium identity");
  check(MovCompatibilityCache.sameSelectedSource(alias,path),"regular cache path lost source identity");
  check("video/mp4".equals(android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(android.webkit.MimeTypeMap.getFileExtensionFromUrl(path))),"regular cache path lost MP4 MIME");
  Class<?> builderType=Class.forName("X.6HE");Object builder=builderType.getConstructor().newInstance();builderType.getMethod("A01",String.class).invoke(builder,path);
  builderType.getField("A05").setInt(builder,1000);Object segment=builderType.getMethod("A00").invoke(builder);
  check(output.equals(segment.getClass().getField("A0I").get(segment)),"actual segment factory lost cached source");
  mediumClass.getField("A0e").set(medium,"ordinary.mp4");check("ordinary.mp4".equals(MovCompatibilityCache.preparedImportPath(medium)),"ordinary import changed");
  mediumClass.getField("A0e").set(medium,"uncached.mov");check("uncached.mov".equals(MovCompatibilityCache.preparedImportPath(medium)),"uncached import changed");
  check(!new String(ClassFileRewriter.maybeRewrite(raw.clone(),"unrelated.Class").bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains("preparedImportPath"),"unrelated class received import adapter");
 }
 static java.lang.reflect.Method method(String name,Class<?>...types)throws Exception{var m=android.media.MediaPlayer.class.getDeclaredMethod(name,types);m.setAccessible(true);return m;}
 static void frames(String path)throws Exception{
  var open=method("nativeVideoOpen",String.class);var info=method("nativeVideoInfo",long.class);var frame=method("nativeVideoFrame",long.class);var command=method("nativeVideoCommand",long.class,int.class,double.class);var close=method("nativeVideoClose",long.class);
  long h=(Long)open.invoke(null,path);check(h!=0,"cached MP4 did not open in AVPlayer");Set<Long> hashes=new HashSet<>();long deadline=System.nanoTime()+5_000_000_000L;
  try{while(System.nanoTime()<deadline){long[] state=(long[])info.invoke(null,h);if(state!=null&&state[3]==1){command.invoke(null,h,1,1.0);break;}Thread.sleep(10);}
   while(System.nanoTime()<deadline&&hashes.size()<3){long[] value=(long[])frame.invoke(null,h);if(value!=null){try{byte[] pixels=new byte[(int)(value[1]*value[2]*4)];int[] dims=new int[3];int result=NativeMedia.nativeVidFrameBgra(value[0],pixels,dims);check(result==0,"AVPlayer frame copy failed");java.util.zip.CRC32 crc=new java.util.zip.CRC32();crc.update(pixels);hashes.add(crc.getValue());}finally{NativeMedia.nativeVidReleaseFrame(value[0]);}}Thread.sleep(30);}
  }finally{close.invoke(null,h);}check(hashes.size()>=3,"cached MP4 frames did not change");
 }
 public static void main(String[]args)throws Throwable{
  System.load(args[0]);Path root=Path.of(args[1]),original=root.resolve("owned clip.mov");byte[] bytes=Files.readAllBytes(original);Object inode=Files.getAttribute(original,"unix:ino");var stamp=Files.getLastModifiedTime(original);
  Context context=new Context(){public String getPackageName(){return "com.instagram.android";}public Resources getResources(){return new Resources(null,null,null);}public android.content.res.AssetManager getAssets(){return null;}public Context getApplicationContext(){return this;}public ClassLoader getClassLoader(){return getClass().getClassLoader();}public java.io.File getFilesDir(){return root.toFile();}public java.io.File getCacheDir(){return root.resolve("cache").toFile();}public java.io.File getDir(String n,int m){return root.toFile();}public ContentResolver getContentResolver(){return resolver;}final ContentResolver resolver=new ContentResolver();};
  String alias=DocumentPickerHandler.macapkReadOnlySelectedMedia(original.toString());
  var first=MovCompatibilityCache.prepare(context,original.toFile(),alias);var concurrent=MovCompatibilityCache.prepare(context,original.toFile(),alias);check(first==concurrent,"same revision started two conversions");
  var output=first.get(130,java.util.concurrent.TimeUnit.SECONDS);check(output.isFile()&&output.getName().endsWith(".mp4"),"atomic MP4 output missing");var cachedStamp=Files.getLastModifiedTime(output.toPath());
  var provider=new MediaStoreProvider();var providerInfo=new ProviderInfo();providerInfo.authority="media";provider.attachInfo(context,providerInfo);check(provider.onCreate(),"provider setup");ContentProviderRegistry.register("media",provider);
  var uri=MediaStoreProvider.macapkImportMedia(context,original.toFile());String galleryAlias=MediaStoreProvider.macapkPrepareSelectedVideo(alias).get(5,java.util.concurrent.TimeUnit.SECONDS);
  check(MovCompatibilityCache.sameSelectedSource(alias,galleryAlias),"original and derived aliases lost logical identity");
  check(MovCompatibilityCache.prepare(context,original.toFile(),alias).get().equals(output),"Browse did not reuse cached revision");check(cachedStamp.equals(Files.getLastModifiedTime(output.toPath())),"cache hit rewrote MP4");
  check(MovCompatibilityCache.snapshotForSelectedUri(uri).state()==MovCompatibilityCache.State.READY,"conversion state missing");frames(galleryAlias);
  importedModel(alias,output);
  if(Files.getFileStore(output.toPath()).supportsFileAttributeView("posix"))check(Files.getPosixFilePermissions(output.toPath()).equals(java.nio.file.attribute.PosixFilePermissions.fromString("r--------")),"prepared MP4 not owner read-only");
  check(MediaStoreProvider.macapkSelectedPathForUri(uri).equals(galleryAlias),"URI reader did not use ready MP4");
  try(var row=context.getContentResolver().query(uri,new String[]{"_data"},null,null,null)){check(row.moveToFirst()&&alias.equals(row.getString(0)),"derived reader changed stable DATA");}
  try(var input=context.getContentResolver().openInputStream(uri)){check(Arrays.equals(input.readAllBytes(),Files.readAllBytes(output.toPath())),"content reader did not use cached MP4 bytes");}
  var retriever=new com.facebook.ffmpeg.FFMpegMediaMetadataRetriever();MediaStoreProvider.macapkInitializeSelectedRetriever(retriever,alias);check(Arrays.equals(retriever.bytes,Files.readAllBytes(output.toPath())),"native metadata hook did not use cached MP4");
  Files.delete(output.toPath());check(MovCompatibilityCache.prepare(context,original.toFile(),alias).get(130,java.util.concurrent.TimeUnit.SECONDS).isFile(),"cache deletion left stale READY future");
  if(Files.getFileStore(output.toPath()).supportsFileAttributeView("posix"))Files.setPosixFilePermissions(output.toPath(),java.nio.file.attribute.PosixFilePermissions.fromString("rw-------"));
  Files.write(output.toPath(),new byte[]{1,2,3});check(MovCompatibilityCache.prepare(context,original.toFile(),alias).get(130,java.util.concurrent.TimeUnit.SECONDS).length()>3,"corrupt cache was reused");
  Path fallback=root.resolve("fallback.mov");String fallbackAlias=DocumentPickerHandler.macapkReadOnlySelectedMedia(fallback.toString());var compatible=MovCompatibilityCache.prepare(context,fallback.toFile(),fallbackAlias).get(130,java.util.concurrent.TimeUnit.SECONDS);
  long tracks=NativeMedia.nativeExtractorOpen(compatible.getPath());check(tracks!=0,"fallback MP4 tracks missing");boolean avc=false,aac=false;for(int i=0;i<NativeMedia.nativeExtractorTrackCount(tracks);i++){String mime=NativeMedia.nativeExtractorFormat(tracks,i).getString("mime");avc|=mime.equals("video/avc");aac|=mime.equals("audio/mp4a-latm");}NativeMedia.nativeExtractorClose(tracks);check(avc&&aac,"fallback did not encode H264/AAC");frames(compatible.getPath());
  check(Arrays.equals(bytes,Files.readAllBytes(original))&&inode.equals(Files.getAttribute(original,"unix:ino"))&&stamp.equals(Files.getLastModifiedTime(original)),"conversion changed original bytes/inode/mtime");
  Files.setLastModifiedTime(original,java.nio.file.attribute.FileTime.fromMillis(stamp.toMillis()+2000));var changed=MovCompatibilityCache.prepare(context,original.toFile(),alias).get(130,java.util.concurrent.TimeUnit.SECONDS);check(!changed.equals(output),"changed source reused stale key");check(Arrays.equals(bytes,Files.readAllBytes(original)),"revision test changed original bytes");
  try(var files=Files.list(output.toPath().getParent())){check(files.noneMatch(p->p.getFileName().toString().contains(".part")),"staging output leaked");}provider.shutdown();System.out.println("PASS MOV cache: concurrent single job, Browse/gallery reuse, unchanged cached mtime, changed revision key, unchanged original, atomic cleanup and changing AVPlayer frames");
 }
}'''

original_run = backend.run


def run(args, **kwargs):
    args = list(args)
    if APP_CLASSES and Path(str(args[0])).name in ("javac","java"):
        index=args.index("-cp")+1
        args[index]=str(args[index])+os.pathsep+str(APP_CLASSES)
        if Path(str(args[0])).name=="java":args.insert(1,"-Dmacapk.test.appClasses="+str(APP_CLASSES))
    if Path(str(args[0])).name == "javac":
        source = Path(sys.argv[sys.argv.index("--source") + 1]) / "runtime/java"
        if not BUILT_ONLY:args.extend(source / name for name in (
            "com/macapk/loader/MovCompatibilityCache.java",
            "com/macapk/loader/DocumentPickerHandler.java",
            "android/provider/MediaStoreProvider.java"))
        if not BUILT_REWRITER:args.append(source / "com/macapk/loader/ClassFileRewriter.java")
        root = next(Path(item).parent for item in args if str(item).endswith("ContentExtractorContract.java"))
        stub = root / "FFMpegMediaMetadataRetriever.java"
        stub.write_text(references.METADATA_STUB)
        args.append(stub)
    result = original_run(args, **kwargs)
    if Path(str(args[0])).name == "ffmpeg" and str(args[-1]).endswith("owned clip.mov"):
        original_run([args[0], "-hide_banner", "-loglevel", "error", "-i", args[-1],
                      "-c:v", "prores_ks", "-profile:v", "0", "-c:a", "copy",
                      Path(args[-1]).parent / "fallback.mov"])
    return result


backend.run = run
if __name__ == "__main__":
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument("--app-classes",type=Path);parser.add_argument("--built-rewriter",action="store_true");parser.add_argument("--built-only",action="store_true")
    extra,rest=parser.parse_known_args();APP_CLASSES=extra.app_classes;BUILT_ONLY=extra.built_only;BUILT_REWRITER=extra.built_rewriter or BUILT_ONLY;sys.argv=[sys.argv[0],*rest]
    backend.main()
