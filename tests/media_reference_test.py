"""Headless selected-media provider and Darwin read-only alias contract."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

BRIDGE = r'''
#include <jni.h>
namespace macapk { void RegisterDocumentPickerMethods(JNIEnv*); namespace osnative { void RegisterNativeOsMethods(JNIEnv*); } }
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void*) {
 JNIEnv* env=nullptr;
 if(vm->GetEnv((void**)&env,JNI_VERSION_21)!=JNI_OK)return JNI_ERR;
 macapk::RegisterDocumentPickerMethods(env); macapk::osnative::RegisterNativeOsMethods(env);
 return JNI_VERSION_21;
}
'''

METADATA_STUB = r'''package com.facebook.ffmpeg;
public final class FFMpegMediaMetadataRetriever {
 public byte[] bytes;public static volatile boolean fail;
 private void nativeInit(String path)throws java.io.IOException {
  if(fail)throw new java.io.IOException("owned metadata failure");
  try(var input=new java.io.FileInputStream(path)){bytes=input.readAllBytes();}
 }
}'''

JAVA = r'''
package com.macapk.loader;
import android.content.*;
import android.content.pm.ProviderInfo;
import android.content.res.Resources;
import android.database.sqlite.SQLiteDatabase;
import android.net.Uri;
import android.provider.*;
import android.os.ParcelFileDescriptor;
import java.nio.file.*;
import java.util.*;
public final class SelectedMediaReferenceTest {
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 interface Action {void run()throws Exception;}
 static void denied(Action action)throws Exception{try{action.run();}catch(java.io.IOException|SecurityException expected){return;}throw new AssertionError("write operation succeeded");}
 static void actualMedium(String appClasses,String alias,String expected)throws Exception{
  String name="com.instagram.common.gallery.Medium";
  byte[] raw;try(var jar=new java.util.jar.JarFile(appClasses);var input=jar.getInputStream(jar.getJarEntry(name.replace('.','/')+".class"))){raw=input.readAllBytes();}
  var rewritten=ClassFileRewriter.maybeRewrite(raw.clone(),name);
  class Isolated extends ClassLoader{Isolated(){super(SelectedMediaReferenceTest.class.getClassLoader());}Class<?> define(byte[] code){return defineClass(name,code,0,code.length);}}
  Class<?> medium=new Isolated().define(rewritten.bytes);Object item=medium.getConstructor().newInstance();
  medium.getField("A0e").set(item,alias);
  check(expected.equals(medium.getMethod("A03").invoke(item)),"actual selected Medium MIME was not restored");
  medium.getField("A0e").set(item,"ordinary.mp4");check("video/mp4".equals(medium.getMethod("A03").invoke(item)),"ordinary Medium MIME changed");
  medium.getField("A0e").set(item,"/dev/fd/999999");check(medium.getMethod("A03").invoke(item)==null,"unknown descriptor gained MIME");
  String marker="macapkFileExtensionForSelectedData";
  check(!new String(ClassFileRewriter.maybeRewrite(raw.clone(),"unrelated.Class").bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains(marker),"unrelated class was patched");
  byte[] changed=raw.clone();changed[5]^=1;
  check(!new String(ClassFileRewriter.maybeRewrite(changed,name).bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains(marker),"changed class fingerprint was patched");
 }
 public static class CanonicalClient {
  public static String path(java.io.File file)throws Exception{return file.getCanonicalPath();}
  public static java.io.File file(java.io.File file)throws Exception{return file.getCanonicalFile();}
 }
 static void selectedCanonical(String alias,Path original)throws Exception{
  String name=CanonicalClient.class.getName();byte[] raw;
  try(var input=CanonicalClient.class.getResourceAsStream("SelectedMediaReferenceTest$CanonicalClient.class")){raw=input.readAllBytes();}
  byte[] rewritten=ClassFileRewriter.maybeRewrite(raw,name).bytes;
  class Isolated extends ClassLoader {Isolated(){super(SelectedMediaReferenceTest.class.getClassLoader());}Class<?> define(){return defineClass(name,rewritten,0,rewritten.length);}}
  Class<?> client=new Isolated().define();
  var path=client.getMethod("path",java.io.File.class);var file=client.getMethod("file",java.io.File.class);
  java.io.File reference=new java.io.File(alias);
  check(alias.equals(path.invoke(null,reference)),"selected canonical path lost descriptor capability");
  java.io.File canonical=(java.io.File)file.invoke(null,reference);
  check(alias.equals(canonical.getPath())&&canonical.isFile(),"selected canonical File is unavailable");
  try(var fresh=DocumentPickerHandler.macapkOpenSelectedMedia(canonical.getPath())){check(fresh.getStatSize()==Files.size(original),"canonical selected source changed");}
  java.io.File ordinary=original.getParent().resolve(".").resolve(original.getFileName()).toFile();
  check(ordinary.getCanonicalPath().equals(path.invoke(null,ordinary)),"ordinary canonical path changed");
  check(ordinary.getCanonicalFile().equals(file.invoke(null,ordinary)),"ordinary canonical File changed");
  int ordinaryFd=NativeOs.open(original.toString(),0,0);check(ordinaryFd>=0,"ordinary descriptor failed");
  try{
   java.io.File other=new java.io.File("/dev/fd/"+ordinaryFd);
   check(!DocumentPickerHandler.macapkIsSelectedMediaReference(other.getPath()),"ordinary FD registered");
   check(other.getCanonicalPath().equals(path.invoke(null,other)),"unregistered canonical FD changed");
  }finally{NativeOs.close(ordinaryFd);}
 }
 static void selectedMetadata(String appClasses,Uri uri,String alias,Path original)throws Exception{
  selectedCanonical(alias,original);
  check(alias.equals(MediaStoreProvider.macapkSelectedPathForUri(uri)),"selected URI did not resolve to read-only alias");
  long selectedId=ContentUris.parseId(uri);
  for(String wrong:new String[]{"content://media/external/video/media/"+selectedId,"content://media/internal/images/media/"+selectedId,"content://media/unknown/images/media/"+selectedId}){
   Uri value=Uri.parse(wrong);check(Objects.equals(value.getPath(),MediaStoreProvider.macapkSelectedPathForUri(value)),"wrong collection or volume resolved selected row");
  }
  for(String other:new String[]{"content://other/external/video/media/1","content://media/external/video/media/99999999","file:///ordinary.mov","content://media/external/video/thumbnails/1"}){
   Uri value=Uri.parse(other);check(Objects.equals(value.getPath(),MediaStoreProvider.macapkSelectedPathForUri(value)),"unselected URI changed");
  }
  byte[] expected=Files.readAllBytes(original);
  int anchor=Integer.parseInt(alias.substring(8));long offset=NativeOs.lseek(anchor,0,1);
  var tasks=new ArrayList<java.util.concurrent.Callable<Boolean>>();
  for(int i=0;i<12;i++)tasks.add(()->{var reader=new com.facebook.ffmpeg.FFMpegMediaMetadataRetriever();
   try{MediaStoreProvider.macapkInitializeSelectedRetriever(reader,alias);}catch(Throwable failure){throw new RuntimeException(failure);}
   return Arrays.equals(expected,reader.bytes);});
  var pool=java.util.concurrent.Executors.newFixedThreadPool(4);
  try{for(var result:pool.invokeAll(tasks))check(result.get(),"metadata initialization shared descriptor cursor");}finally{pool.shutdownNow();}
  check(NativeOs.lseek(anchor,0,1)==offset,"metadata initialization advanced registry anchor");
  var ordinary=new com.facebook.ffmpeg.FFMpegMediaMetadataRetriever();
  try{MediaStoreProvider.macapkInitializeSelectedRetriever(ordinary,original.toString());}catch(Throwable failure){throw new RuntimeException(failure);}
  check(Arrays.equals(expected,ordinary.bytes),"ordinary native metadata path changed");
  com.facebook.ffmpeg.FFMpegMediaMetadataRetriever.fail=true;
  try{MediaStoreProvider.macapkInitializeSelectedRetriever(ordinary,alias);throw new AssertionError("native failure swallowed");}
  catch(java.io.IOException expectedFailure){check("owned metadata failure".equals(expectedFailure.getMessage()),"native cause changed");}
  catch(Throwable unexpected){throw new RuntimeException(unexpected);}finally{com.facebook.ffmpeg.FFMpegMediaMetadataRetriever.fail=false;}
  if(appClasses==null)return;
  Class<?> factory=Class.forName("X.3TX");
  Object rebuilt=factory.getMethod("A05",java.io.File.class).invoke(factory.getConstructor().newInstance(),new java.io.File(alias));
  check(rebuilt.getClass().getField("A0A").getInt(rebuilt)==3,"actual video factory lost numeric descriptor video type");
  check(alias.equals(rebuilt.getClass().getField("A0e").get(rebuilt)),"actual video factory changed descriptor source");
  byte[] importRaw;try(var jar=new java.util.jar.JarFile(appClasses);var in=jar.getInputStream(jar.getJarEntry("X/LQe.class"))){importRaw=in.readAllBytes();}
  byte[] importPatched=ClassFileRewriter.maybeRewrite(importRaw,"X.LQe").bytes;
  check(new String(importPatched,java.nio.charset.StandardCharsets.ISO_8859_1).contains("macapkCanonicalSelectedPath"),"actual importer canonical callsite not routed");
  class VerifiedImport extends ClassLoader{VerifiedImport(){super(SelectedMediaReferenceTest.class.getClassLoader());}Class<?> define(){return defineClass("X.LQe",importPatched,0,importPatched.length);}}
  new VerifiedImport().define().getDeclaredMethods();
  for(String name:new String[]{"X.HBa","com.facebook.ffmpeg.FFMpegMediaMetadataRetriever"}){
   byte[] raw;try(var jar=new java.util.jar.JarFile(appClasses);var in=jar.getInputStream(jar.getJarEntry(name.replace('.','/')+".class"))){raw=in.readAllBytes();}
   byte[] patched=ClassFileRewriter.maybeRewrite(raw.clone(),name).bytes;
   String marker=name.equals("X.HBa")?"macapkSelectedPathForUri":"macapkInitializeSelectedRetriever";
   check(new String(patched,java.nio.charset.StandardCharsets.ISO_8859_1).contains(marker),"actual metadata callsite not patched");
   class Verified extends ClassLoader{Verified(){super(SelectedMediaReferenceTest.class.getClassLoader());}Class<?> define(){return defineClass(name,patched,0,patched.length);}}
   new Verified().define().getDeclaredMethods();
   check(!new String(ClassFileRewriter.maybeRewrite(raw.clone(),"unrelated.Class").bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains(marker),"unrelated metadata class changed");
   raw[5]^=1;check(!new String(ClassFileRewriter.maybeRewrite(raw,name).bytes,java.nio.charset.StandardCharsets.ISO_8859_1).contains(marker),"changed metadata fingerprint patched");
  }
 }
 public static void main(String[] args)throws Exception{
  System.load(args[0]);System.load(args[1]);Path root=Path.of(args[2]);String phase=args[3];
  Path original=root.resolve("selected clip ü.PNG");
  if(phase.equals("create")||phase.equals("sibling"))javax.imageio.ImageIO.write(new java.awt.image.BufferedImage(3,2,1),"png",original.toFile());
  var held=new ArrayList<java.io.FileInputStream>();
  if(phase.equals("reopen"))for(int i=0;i<24;i++)held.add(new java.io.FileInputStream(original.toFile()));
  var resolver=new ContentResolver();
  Context context=new Context(){
   public String getPackageName(){return phase.equals("sibling")?"org.macapk.synthetic":"com.instagram.android";}
   public Resources getResources(){return new Resources(null,null,null);}
   public android.content.res.AssetManager getAssets(){return null;}
   public Context getApplicationContext(){return this;}
   public ClassLoader getClassLoader(){return getClass().getClassLoader();}
   public java.io.File getFilesDir(){return root.toFile();}
   public java.io.File getCacheDir(){return root.toFile();}
   public java.io.File getDir(String name,int mode){return root.toFile();}
   public ContentResolver getContentResolver(){return resolver;}
  };
  var provider=new MediaStoreProvider();var info=new ProviderInfo();info.authority=MediaStore.AUTHORITY;
  provider.attachInfo(context,info);check(provider.onCreate(),"provider initialization");ContentProviderRegistry.register(info.authority,provider);
  var databaseField=MediaStoreProvider.class.getDeclaredField("mDb");databaseField.setAccessible(true);
  var policyDatabase=(SQLiteDatabase)databaseField.get(provider);
  try(var tables=policyDatabase.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name='macapk_photos'",null)){
   check((tables.getCount()>0)==phase.equals("sibling"),"PhotoKit package schema scope");
  }
  if(phase.equals("sibling")){
   Path external=android.os.Environment.getExternalStorageDirectory().toPath();Files.createDirectories(external.resolve("DCIM"));
   Path library=external.resolve("DCIM/library.png");Files.copy(original,library);
   Uri found=null;long deadline=System.nanoTime()+3_000_000_000L;
   while(found==null&&System.nanoTime()<deadline){
    try(var cursor=resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,new String[]{"_id","_data"},null,null,null)){
     while(cursor.moveToNext())if(library.toString().equals(cursor.getString(1)))found=ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,cursor.getLong(0));
    }
    if(found==null)Thread.sleep(10);
   }
   check(found!=null,"unrelated app lost normal library scan/query");
   try(var stream=resolver.openInputStream(found)){check(Arrays.equals(Files.readAllBytes(original),stream.readAllBytes()),"unrelated app normal reader failed");}
   try(var descriptor=resolver.openFileDescriptor(found,"rw")){check(descriptor!=null,"unrelated app permitted write mode changed");}
   check("image/png".equals(resolver.getType(found)),"unrelated app MIME changed");
   provider.shutdown();System.out.println("PASS: unrelated app keeps library scan/query, PhotoKit policy, normal read/write open and MIME");return;
  }
  if(phase.equals("missing")){
   try(var cursor=resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,new String[]{"_id"},null,null,null)){check(cursor.getCount()==0,"missing reference remained visible");}
   provider.shutdown();System.out.println("PASS: missing reference hidden without scanning");return;
  }
  byte[] bytes=Files.readAllBytes(original);String sha=HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes));
  Object inode=Files.getAttribute(original,"unix:ino");var modified=Files.getLastModifiedTime(original);
  int ordinary=NativeOs.open(original.toString(),0,0);check(ordinary>=0,"ordinary reader open failed");
  String ordinaryAlias="/dev/fd/"+ordinary;
  check(!DocumentPickerHandler.macapkIsSelectedMediaReference(ordinaryAlias),"ordinary descriptor treated as selected");
  var ordinaryBitmap=android.graphics.BitmapFactory.decodeFile(ordinaryAlias);
  check(ordinaryBitmap!=null&&ordinaryBitmap.getWidth()==3,"ordinary descriptor image stopped decoding");ordinaryBitmap.recycle();NativeOs.close(ordinary);
  Uri item;
  if(phase.equals("create")){
   Path external=android.os.Environment.getExternalStorageDirectory().toPath();Files.createDirectories(external.resolve("DCIM"));
   Path unselected=external.resolve("DCIM/unselected.png");Files.write(unselected,bytes);
   var field=MediaStoreProvider.class.getDeclaredField("mDb");field.setAccessible(true);var db=(SQLiteDatabase)field.get(provider);
   var old=new ContentValues();old.put("_data",unselected.toString());old.put("media_type",1);old.put("owner_package_name",context.getPackageName());db.insert("files",null,old);
   try(var cursor=resolver.query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,new String[]{"_id"},null,null,null)){check(cursor.getCount()==0,"unselected legacy row leaked");}
   check(DocumentPickerHandler.importPickedMedia(context,null)==null,"cancel imported media");
   item=DocumentPickerHandler.importPickedMedia(context,new String[]{original.toString()});check(item!=null,"selection did not produce URI");Files.writeString(root.resolve("selected-uri.txt"),item.toString());
   check(!Files.exists(external.resolve("DCIM/Mac Imports")),"selection copied original into import library");
  }else item=Uri.parse(Files.readString(root.resolve("selected-uri.txt")));
  String alias;
  try(var row=resolver.query(item,new String[]{"_data","width","height","mime_type","_display_name"},null,null,null)){
   check(row.moveToFirst(),"selected reference hidden");alias=row.getString(0);
   check(alias.startsWith("/dev/fd/"),"original path exposed instead of read-only alias");
   check(row.getInt(1)==3&&row.getInt(2)==2&&row.getString(3).equals("image/png")&&row.getString(4).equals("selected clip ü.PNG"),"selected metadata");
  }
  Path reference=Path.of(alias);check(reference.toFile().isFile(),"alias is not a regular file to Java");
  check(DocumentPickerHandler.macapkIsSelectedMediaReference(alias),"selected descriptor missing registry membership");
  var selectedSnapshot=MediaStoreProvider.macapkSelectedReferenceSnapshot();
  check(selectedSnapshot.size()==1&&alias.equals(selectedSnapshot.get((int)android.content.ContentUris.parseId(item))),"gallery snapshot did not contain only the current selected reference");
  selectedMetadata(args.length>4?args[4]:null,item,alias,original);
  if(args.length>4)actualMedium(args[4],alias,"image/png");
  check(Arrays.equals(bytes,Files.readAllBytes(reference)),"alias read changed bytes");
  int anchor=Integer.parseInt(alias.substring(8));check(NativeOs.lseek(anchor,7,0)==7,"could not offset anchor for decode test");
  for(int repeat=0;repeat<3;repeat++){
   var bounds=new android.graphics.BitmapFactory.Options();bounds.inJustDecodeBounds=true;
   android.graphics.BitmapFactory.decodeFile(alias,bounds);check(bounds.outWidth==3&&bounds.outHeight==2,"repeated alias bounds decode failed");
   var bitmap=android.graphics.BitmapFactory.decodeFile(alias);check(bitmap!=null&&bitmap.getWidth()==3&&bitmap.getHeight()==2,"repeated alias raster decode failed");bitmap.recycle();
   check(NativeOs.lseek(anchor,0,1)==7,"SDK decoder changed anchor offset");
  }
  if(phase.equals("create"))Files.writeString(root.resolve("old-alias.txt"),alias);
  else check(!alias.equals(Files.readString(root.resolve("old-alias.txt"))),"restart test did not exercise a changed descriptor");
  for(String mode:new String[]{"w","wt","wa","rw","rwt"})denied(()->resolver.openFileDescriptor(item,mode));
  denied(()->new java.io.RandomAccessFile(reference.toFile(),"rw"));
  denied(()->new java.io.FileOutputStream(reference.toFile(),false));
  denied(()->new java.io.FileOutputStream(reference.toFile(),true));
  denied(()->ParcelFileDescriptor.open(reference.toFile(),ParcelFileDescriptor.MODE_READ_WRITE));
  denied(()->Files.delete(reference));denied(()->Files.move(reference,root.resolve("renamed.png")));
  for(int flags:new int[]{1,2,1|512,1|1024})check(NativeOs.open(alias,flags,0600)<0,"native write open succeeded");
  int fd=Integer.parseInt(alias.substring(8));check(NativeOs.ftruncate(fd,0)<0,"native truncate succeeded");
  check(NativeOs.write(fd,new byte[]{1},0,1)<0,"native write succeeded");
  try(var stream=resolver.openInputStream(item)){check(Arrays.equals(bytes,stream.readAllBytes()),"provider read failed");}
  check(sha.equals(HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(original)))),"original SHA changed");
  check(inode.equals(Files.getAttribute(original,"unix:ino"))&&modified.equals(Files.getLastModifiedTime(original)),"original inode or time changed");
  check(provider.delete(item,null,null)==0,"provider deleted selected original");
  if(phase.equals("reopen")){
   Files.delete(original); // Simulate the owner removing this synthetic source after selection.
   check(DocumentPickerHandler.macapkIsSelectedMediaReference(alias),"removed selected reference lost registry identity");
   check(android.graphics.BitmapFactory.decodeFile(alias)==null,"removed selected reference fell back to stale anchor bytes");
  }
  provider.shutdown();for(var file:held)file.close();
  System.out.println("PASS: "+phase+"; selected-only; no-copy; same original inode/SHA/time; provider and Java/native alias writes/truncate/delete/rename denied");
 }
}
'''


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, timeout=120, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--jdk-home", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--app-classes",type=Path,help="Optional public Instagram 445 converted classes.jar")
    parser.add_argument("--rewriter-source-overlay",action="store_true")
    parser.add_argument("--built-only",action="store_true",help="Use built runtime JARs without compiling runtime source overlays")
    options = parser.parse_args()
    if options.built_only and options.rewriter_source_overlay:parser.error("--built-only cannot use a rewriter source overlay")
    source, jdk = options.source.resolve(), options.jdk_home.resolve()
    options.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="selected-reference-", dir=options.work_root) as temporary:
        root = Path(temporary)
        (root / "bridge.mm").write_text(BRIDGE)
        (root / "SelectedMediaReferenceTest.java").write_text(JAVA)
        (root / "FFMpegMediaMetadataRetriever.java").write_text(METADATA_STUB)
        (root / "classes").mkdir()
        (root / "data").mkdir()
        includes = ["-I" + str(jdk / "include"), "-I" + str(jdk / "include/darwin")]
        run(["clang++", "-dynamiclib", "-std=c++17", *includes, "-I" + str(source / "runtime/include"),
             source / "runtime/src/native_sqlite.cpp", "-lsqlite3", "-framework", "CoreFoundation", "-o", root / "sqlite.dylib"])
        run(["clang++", "-dynamiclib", "-std=c++17", "-fobjc-arc", "-Wno-deprecated-declarations", *includes,
             source / "runtime/src/document_picker.mm", source / "runtime/src/native_os.cpp", root / "bridge.mm",
             "-framework", "AppKit", "-framework", "UniformTypeIdentifiers", "-framework", "AVFoundation",
             "-framework", "CoreMedia", "-framework", "ImageIO", "-lcompression", "-o", root / "picker.dylib"])
        classpath = str(source / "runtime/build/lib/android-framework.jar") + ":" + str(source / "runtime/build/lib/macapk-loader.jar")
        if options.app_classes:classpath += os.pathsep + str(options.app_classes.resolve())
        rewriter_sources=[source / "runtime/java/com/macapk/loader/ClassFileRewriter.java"] if options.rewriter_source_overlay else []
        runtime_sources=[] if options.built_only else [source / "runtime/java" / name for name in
            ("com/macapk/loader/NativeOs.java","android/provider/MediaStoreProvider.java",
             "com/macapk/loader/DocumentPickerHandler.java","android/graphics/BitmapFactory.java")]
        run([jdk / "bin/javac", "-cp", classpath, "-d", root / "classes",
             *runtime_sources,*rewriter_sources,root / "SelectedMediaReferenceTest.java",root / "FFMpegMediaMetadataRetriever.java"])
        (root / "photos-fixture").mkdir()
        env = dict(os.environ, MACAPK_LOG_LEVEL="99", MACAPK_ANDROID_ROOT=str(root / "android"), MACAPK_MEDIASTORE_ACCESS="0",
                   MACAPK_PHOTOKIT="1", MACAPK_PHOTOKIT_SOURCE_DIR=str(root / "photos-fixture"))
        for phase in ("create", "reopen", "missing", "sibling"):
            if phase == "missing":
                (root / "data/selected clip ü.PNG").unlink(missing_ok=True)
            if phase == "sibling":
                env["MACAPK_ANDROID_ROOT"] = str(root / "sibling-android")
            app_args=[options.app_classes.resolve()] if options.app_classes else []
            run([jdk / "bin/java", "--add-opens=java.base/java.io=ALL-UNNAMED", "-Djava.awt.headless=true", "-cp", str(root / "classes") + ":" + classpath,
                 "com.macapk.loader.SelectedMediaReferenceTest", root / "sqlite.dylib", root / "picker.dylib", root / "data", phase,*app_args], env=env)


if __name__ == "__main__":
    main()
