#!/usr/bin/env bash
set -euo pipefail
commit=339f3242c761f16c27e5ffcde1d35dcc31933a55
work=${LLAMA_BUILD_ROOT:-$PWD/llama-build}
mkdir -p "$work"
archive="$work/source.tar.gz"
if [[ ! -f "$archive" ]]; then
    curl -fL --retry 3 "https://codeload.github.com/ggml-org/llama.cpp/tar.gz/$commit" -o "$archive.partial"
    mv "$archive.partial" "$archive"
fi
printf '%s  %s\n' 901a2a2b2eb389a08cae3fec3269914f5c03e8d39b1352db9a29cbd1886727f3 "$archive" | sha256sum -c -
source_dir="$work/llama.cpp-$commit"
[[ -d "$source_dir" ]] || tar -xzf "$archive" -C "$work"
features=$(awk -F: '/^Features/ {print $2; exit}' /proc/cpuinfo)
arch=armv8-a
if [[ " $features " == *' asimdhp '* ]]; then arch=armv8.2-a+fp16; fi
if [[ " $features " == *' asimddp '* ]]; then
    if [[ $arch == armv8-a ]]; then arch=armv8.2-a+dotprod; else arch="$arch+dotprod"; fi
fi
cmake -S "$source_dir" -B "$work/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
    -DGGML_CPU=ON -DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH="$arch" \
    -DGGML_CANN=OFF -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_BLAS=OFF \
    -DGGML_CPU_KLEIDIAI=OFF -DGGML_OPENMP=ON -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_OPENSSL=OFF -DLLAMA_LLGUIDANCE=OFF -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build "$work/build" --parallel 2 --target llama-server
echo "Built: $work/build/bin/llama-server"
