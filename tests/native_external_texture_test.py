#!/usr/bin/env python3
"""Render real pixels through the production ARM64 guest external-texture bridges."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import gl_external_texture_test as fixture

NAMES = ("glShaderSource", "glBindTexture", "glTexParameteri", "glGetIntegerv", "glGetShaderiv", "glGetShaderSource")


def block(source, name):
    start = source.index("// " + name + "_BEGIN")
    return source[start:source.index("// " + name + "_END", start)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--unadapted", action="store_true", help="Reproduce the prior bare ANGLE guest dispatch")
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=True)
    source = (args.source / "runtime/translator/src/bionic_shim.cpp").read_text()
    runtime = (args.source / "runtime/src/native_methods.cpp").read_text()
    bridges = "\n".join("#define __macapk_arm64_" + name + " " + name for name in NAMES) if args.unadapted else (
        "namespace external_texture = macapk::external_texture;\n"
        + block(runtime, "MACAPK_EXTERNAL_TEXTURE_RUNTIME") + "\n" + block(source, "MACAPK_EXTERNAL_TEXTURE_ARM64"))
    adapter = r'''
void NativeShaderSource(GLuint shader,const std::string& source){
 size_t split=source.find("samplerExternalOES");split=split==std::string::npos?source.size()/2:split+8;
 std::string first=source.substr(0,split)+"ignored",second=source.substr(split)+"ignored";
 const GLchar* strings[]={first.data(),second.data()};GLint lengths[]={(GLint)split,(GLint)(source.size()-split)};
 __macapk_arm64_glShaderSource(shader,2,strings,lengths);
 GLint capacity=0;__macapk_arm64_glGetShaderiv(shader,GL_SHADER_SOURCE_LENGTH,&capacity);
 std::vector<char> actual(capacity);GLsizei length=0;__macapk_arm64_glGetShaderSource(shader,capacity,&length,actual.data());
 if(std::string(actual.data(),length)!=source)throw std::runtime_error("native guest shader source query changed");
}
'''
    code = fixture.CPP.replace("SetShaderSource(", "NativeShaderSource(").replace("BindTexture(0x8D65,", "__macapk_arm64_glBindTexture(0x8D65,")
    code = code.replace("glGetIntegerv(Binding(0x8D67),", "__macapk_arm64_glGetIntegerv(0x8D67,")
    code = code.replace("glTexParameteri(Target(0x8D65),", "__macapk_arm64_glTexParameteri(0x8D65,")
    code = code.replace('using namespace macapk::external_texture;', '#include <cstring>\n#include <vector>\n#include <dlfcn.h>\n' + bridges + '\n' + adapter + '\nusing namespace macapk::external_texture;')
    if not args.unadapted:
        code = code.replace('int main(){try{', 'int main(){try{check(macapk_external_texture_guest_symbol("glShaderSource")==reinterpret_cast<void*>(&__macapk_arm64_glShaderSource),"guest proc lookup bypassed adapter");check(macapk_external_texture_guest_symbol("glUniform1i")==nullptr,"unrelated guest proc was intercepted");')
        edge = r'''
  GLuint edge=glCreateShader(GL_FRAGMENT_SHADER);NativeShaderSource(edge,fragment);const GLchar* edgeText=fragment.c_str();
  __macapk_arm64_glShaderSource(edge,-1,&edgeText,nullptr);std::string edgeOriginal;
  check(glGetError()==GL_INVALID_VALUE&&OriginalSource(edge,edgeOriginal)&&edgeOriginal==fragment,"invalid negative shader count changed the retained source");
  __macapk_arm64_glShaderSource(edge,0,&edgeText,nullptr);GLint edgeLength=-1;__macapk_arm64_glGetShaderiv(edge,GL_SHADER_SOURCE_LENGTH,&edgeLength);
  check(!OriginalSource(edge,edgeOriginal)&&edgeLength<=1,"empty shader replacement retained prior external source");
  glDeleteShader(edge);
'''
        code = code.replace("GLuint fs=shader", edge + "GLuint fs=shader")
    angle = (args.source / "thirdparty/angle-prebuilt").resolve()
    with tempfile.TemporaryDirectory(prefix="native-external-", dir=args.work_root) as temporary:
        root = Path(temporary)
        (root / "test.cpp").write_text(code)
        subprocess.run(["clang++", "-std=c++17", "-I" + str(args.source / "runtime/src"), "-I" + str(angle / "include"),
                        str(root / "test.cpp"), "-L" + str(angle / "lib"), "-lEGL", "-lGLESv2", "-Wl,-rpath," + str(angle / "lib"),
                        "-Wl,-export_dynamic", "-o", str(root / "test")], check=True, timeout=60)
        result = subprocess.run([str(root / "test")], cwd=angle / "lib", capture_output=True, text=True, timeout=30)
        if args.unadapted:
            if result.returncode != 1 or "shader did not compile" not in result.stderr:
                raise AssertionError("Prior native shader failure was not reproduced")
            print("PASS prior bare ANGLE native guest dispatch rejects external shader")
        else:
            if result.returncode:
                raise AssertionError("Native external-texture contract failed: " + result.stderr)
            print(result.stdout.strip())


if __name__ == "__main__":
    main()
