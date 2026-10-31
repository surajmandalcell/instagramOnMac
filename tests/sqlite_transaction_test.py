#!/usr/bin/env python3
"""Exercise raw SQL transactions through the real SQLite JNI backend."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

JAVA = r'''
import android.database.sqlite.*;
import java.util.concurrent.*;
public final class SqlTransactionContract {
  static boolean actualAppWrapper;
  static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
  static void sql(SQLiteDatabase db,String text){try(SQLiteStatement statement=db.compileStatement(text)){
    if(actualAppWrapper)try{Object wrapper=Class.forName("X.5pl").getConstructor(SQLiteStatement.class).newInstance(statement);wrapper.getClass().getMethod("BBb").invoke(wrapper);}
    catch(ReflectiveOperationException error){throw new AssertionError("public app statement wrapper failed",error);}
    else statement.execute();
  }}
  static long count(SQLiteDatabase db){try(var cursor=db.rawQuery("SELECT count(*) FROM entries",null)){cursor.moveToFirst();return cursor.getLong(0);}}
  public static void main(String[] args)throws Exception{
    System.load(args[0]);
    actualAppWrapper=args.length>1;
    SQLiteOpenHelper helper=new SQLiteOpenHelper(null,null,null,1){
      public void onCreate(SQLiteDatabase db){
        sql(db,"BEGIN IMMEDIATE");
        db.execSQL("CREATE TABLE entries(value INTEGER)");
        db.execSQL("INSERT INTO entries VALUES(1)");
        sql(db,"COMMIT");
        check(db.inTransaction(),"inner SQL commit ended helper transaction");
      }
      public void onUpgrade(SQLiteDatabase db,int from,int to){throw new AssertionError("unexpected upgrade");}
    };
    SQLiteDatabase db=helper.getWritableDatabase();
    check(count(db)==1&&!db.inTransaction(),"helper migration did not commit");
    db.beginTransaction();sql(db,"BEGIN");db.execSQL("INSERT INTO entries VALUES(2)");sql(db,"ROLLBACK");
    db.setTransactionSuccessful();db.endTransaction();check(count(db)==1,"failed nested SQL transaction did not veto outer commit");
    sql(db,"BEGIN");db.beginTransaction();db.execSQL("INSERT INTO entries VALUES(3)");db.setTransactionSuccessful();db.endTransaction();sql(db,"END");
    check(count(db)==2&&!db.inTransaction(),"mixed API/SQL nesting failed");
    sql(db,"BEGIN");db.execSQL("SAVEPOINT kept");db.execSQL("INSERT INTO entries VALUES(4)");
    db.execSQL("ROLLBACK TO kept");db.execSQL("RELEASE kept");sql(db,"COMMIT");check(count(db)==2,"savepoint rollback was treated as full transaction abort");
    db.execSQL("BEGIN");check(db.inTransaction(),"execSQL BEGIN bypassed transaction ownership");
    CountDownLatch entered=new CountDownLatch(1),finished=new CountDownLatch(1);Throwable[] failure={null};
    Thread writer=new Thread(()->{entered.countDown();try{sql(db,"BEGIN");db.execSQL("INSERT INTO entries VALUES(5)");sql(db,"COMMIT");}catch(Throwable error){failure[0]=error;}finally{finished.countDown();}},"synthetic-sql-writer");
    writer.start();check(entered.await(1,TimeUnit.SECONDS),"foreign writer never started");
    check(!finished.await(100,TimeUnit.MILLISECONDS),"foreign SQL transaction entered another thread's transaction");
    db.execSQL("ROLLBACK");check(finished.await(2,TimeUnit.SECONDS),"foreign writer stayed blocked after release");
    if(failure[0]!=null)throw new AssertionError("foreign writer failed",failure[0]);
    check(count(db)==3,"foreign transaction did not commit independently");
    try(var begin=db.compileStatement("BEGIN");var commit=db.compileStatement("COMMIT")){
      check(begin.executeInsert()==0,"special insert result must be zero");
      check(commit.executeUpdateDelete()==0,"special changed-row result must be zero");
    }
    try(var begin=db.compileStatement("BEGIN");var commit=db.compileStatement("COMMIT")){
      check(begin.simpleQueryForLong()==0,"special scalar result must be zero");
      check(commit.simpleQueryForString()==null,"special string result must be null");
    }
    check(!db.inTransaction(),"transaction remained open");helper.close();
    System.out.println("PASS helper raw-BEGIN migration, mixed nesting, rollback veto, savepoints, thread ownership and special result values");
  }
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True,type=Path)
    parser.add_argument("--jdk-home",required=True,type=Path)
    parser.add_argument("--work-root",required=True,type=Path)
    parser.add_argument("--source-overlay",action="store_true",help="Compile the two changed SQLite classes for a red/green source check")
    parser.add_argument("--app-classes",type=Path,help="Optional public Instagram 445 classes.jar for its actual statement wrapper")
    args=parser.parse_args()
    source=args.source.resolve();jdk=args.jdk_home.resolve();args.work_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sqlite-contract-",dir=args.work_root) as temporary:
        work=Path(temporary);test=work/"SqlTransactionContract.java";test.write_text(JAVA)
        command=["clang++","-dynamiclib","-std=c++17","-I"+str(jdk/"include"),"-I"+str(jdk/"include/darwin"),
                 "-I"+str(source/"runtime/include"),str(source/"runtime/src/native_sqlite.cpp"),"-lsqlite3","-framework","CoreFoundation","-o",str(work/"sqlite.dylib")]
        subprocess.run(command,check=True,timeout=60)
        cp=os.pathsep.join(str(source/"runtime/build/lib"/name) for name in ("android-framework.jar","macapk-loader.jar"))
        if args.app_classes:cp+=os.pathsep+str(args.app_classes.resolve())
        files=[str(test)]
        if args.source_overlay:
            files += [str(source/"runtime/java/android/database/sqlite"/name) for name in ("SQLiteDatabase.java","SQLiteStatement.java")]
        subprocess.run([str(jdk/"bin/javac"),"-cp",cp,"-d",str(work),*files],check=True,timeout=30)
        extra=["public-app-wrapper"] if args.app_classes else []
        subprocess.run([str(jdk/"bin/java"),"-Djava.awt.headless=true","-cp",str(work)+os.pathsep+cp,"SqlTransactionContract",str(work/"sqlite.dylib"),*extra],
                       env=dict(os.environ,MACAPK_LOG_LEVEL="99"),check=True,timeout=15)


if __name__=="__main__":main()
