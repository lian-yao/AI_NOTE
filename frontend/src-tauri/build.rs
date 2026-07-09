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

    let backend_internal = manifest_dir
        .join("bin")
        .join("AiVideoBackend")
        .join("_internal");
    let required_cpu_runtime = [
        backend_internal.join("ctranslate2").join("ctranslate2.dll"),
        backend_internal.join("ctranslate2").join("libiomp5md.dll"),
    ];

    println!("cargo:rerun-if-changed={}", backend_internal.display());

    if let Some(missing_runtime) = required_cpu_runtime.iter().find(|path| !path.exists()) {
        panic!(
            "Release bundle is missing a required AiVideoBackend CPU runtime DLL: {}. \
Rebuild the CPU-only sidecar before packaging; ctranslate2 CPU runtime is required for local transcription.",
            missing_runtime.display()
        );
    }

    if let Some(gpu_artifact) = find_forbidden_gpu_artifact(&backend_internal) {
        panic!(
            "Release bundle is pointing at a GPU-enabled AiVideoBackend sidecar. \
Use the CPU-only sidecar for desktop releases, otherwise CUDA/cuBLAS/cuDNN libraries inflate the installer. \
Found: {}",
            gpu_artifact.display()
        );
    }
}

fn find_forbidden_gpu_artifact(root: &std::path::Path) -> Option<std::path::PathBuf> {
    if !root.exists() {
        return None;
    }

    let mut stack = vec![root.to_path_buf()];
    while let Some(path) = stack.pop() {
        let metadata = match std::fs::metadata(&path) {
            Ok(metadata) => metadata,
            Err(_) => continue,
        };
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();

        if metadata.is_dir() {
            if matches!(
                name.as_str(),
                "nvidia" | "torch" | "torchaudio" | "torchvision"
            ) {
                return Some(path);
            }
            if let Ok(entries) = std::fs::read_dir(&path) {
                stack.extend(entries.flatten().map(|entry| entry.path()));
            }
            continue;
        }

        if name.ends_with(".dll") && (name.starts_with("cublas") || name.starts_with("cudnn")) {
            return Some(path);
        }
    }

    None
}
