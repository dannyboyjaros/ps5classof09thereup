cmake_minimum_required(VERSION 3.16)
project(ClassOf09PS5Runtime C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

find_package(SDL2 REQUIRED)
find_package(SDL2_image REQUIRED)
find_package(SDL2_mixer REQUIRED)
find_package(SDL2_ttf REQUIRED)

add_executable(class09_runtime
    src/main.c
    src/engine.c
    src/json_lite.c
    src/engine.h
    src/json_lite.h)

target_include_directories(class09_runtime PRIVATE src)

# Windows SDL2 builds expose SDL2main separately (it redirects main -> SDL_main).
# It is a static archive, so it must come before the SDL2 import library on the
# link line or its SDL_* references stay unresolved.
set(CLASS09_LIBS)
if(TARGET SDL2::SDL2main)
    list(APPEND CLASS09_LIBS SDL2::SDL2main)
endif()
list(APPEND CLASS09_LIBS
    SDL2::SDL2
    SDL2_image::SDL2_image
    SDL2_mixer::SDL2_mixer
    SDL2_ttf::SDL2_ttf)

option(C09_WEBM "Build the host runtime with libvpx/libvorbis WebM playback" OFF)

target_link_libraries(class09_runtime PRIVATE ${CLASS09_LIBS})

if(C09_WEBM)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(VPX REQUIRED IMPORTED_TARGET vpx)
    pkg_check_modules(VORBIS REQUIRED IMPORTED_TARGET vorbis)
    pkg_check_modules(OGG REQUIRED IMPORTED_TARGET ogg)
    target_sources(class09_runtime PRIVATE src/webm.c src/webm.h)
    target_compile_definitions(class09_runtime PRIVATE C09FS_WEBM=1)
    target_link_libraries(class09_runtime PRIVATE PkgConfig::VPX PkgConfig::VORBIS PkgConfig::OGG)
endif()

if(MSVC)
    target_compile_options(class09_runtime PRIVATE /W3)
else()
    target_compile_options(class09_runtime PRIVATE -Wall -Wextra -Wno-unused-parameter)
endif()
