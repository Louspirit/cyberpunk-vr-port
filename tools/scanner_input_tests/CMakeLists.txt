cmake_minimum_required(VERSION 3.24)
project(ScannerInputTests LANGUAGES CXX)
enable_testing()
add_executable(scanner_input_tests main.cpp)
find_path(CVR_OPENXR_INCLUDE_DIR NAMES openxr/openxr.h
    HINTS "${CMAKE_CURRENT_LIST_DIR}/../../build/_deps/openxr-src/include"
    DOC "OpenXR include directory (from the main build or an installed SDK)" REQUIRED)
target_include_directories(scanner_input_tests PRIVATE ../../include "${CVR_OPENXR_INCLUDE_DIR}")
target_compile_features(scanner_input_tests PRIVATE cxx_std_20)
add_test(NAME scanner_input COMMAND scanner_input_tests)
