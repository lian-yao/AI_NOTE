fn main() {
    prevent_gpu_sidecar_release_bundle();
    tauri_build::build()
}

fn prevent_gpu_sidecar_release_bundle() {
    if std::env::var("PROFILE").as_deref() != Ok("release") {
        return;
    }

    let manifest_dir = std::path::PathBuf::from(
        std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string()),
    );
    let tauri_conf = manifest_dir.join("tauri.conf.json");
    let conf_text = std::fs::read_to_string(&tauri_conf)
        .unwrap_or_default()
        .replace('\\', "/");
    let checks_default_backend = conf_text.contains("bin/AiVideoBackend/AiVideoBackend")
        || conf_text.contains("bin/AiVideoBackend/_internal");
    if !checks_default_backend {
        return;
    }

    let backend_internal = manifest_dir.join("bin").join("AiVideoBackend").join("_internal");
    let gpu_markers = [
        backend_internal.join("nvidia"),
        backend_internal.join("torch"),
        backend_internal.join("torchaudio"),
        backend_internal.join("torchvision"),
        backend_internal.join("ctranslate2").join("cublas64_12.dll"),
        backend_internal.join("ctranslate2").join("cudnn64_9.dll"),
    ];

    println!("cargo:rerun-if-changed={}", backend_internal.display());

    if gpu_markers.iter().any(|path| path.exists()) {
        panic!(
            "Release bundle is pointing at a GPU-enabled AiVideoBackend sidecar. \
Use the CPU-only sidecar for desktop releases, otherwise CUDA/cuBLAS/cuDNN libraries inflate the installer."
        );
    }
}
