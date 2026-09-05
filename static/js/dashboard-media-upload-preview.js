(() => {
    "use strict";

    const initializeUploadPreview = () => {
        const form = document.querySelector("[data-media-upload-preview-form]");
        if (!form) {
            return;
        }

        const fileInput = form.querySelector('input[type="file"][name="file"]');
        const mediaTypeInput = form.querySelector('[name="media_type"]');
        const preview = form.querySelector("[data-media-upload-preview]");
        const image = form.querySelector("[data-media-upload-preview-image]");
        const video = form.querySelector("[data-media-upload-preview-video]");
        const removeButton = form.querySelector("[data-media-upload-preview-remove]");
        if (!fileInput || !preview || !image || !video || !removeButton) {
            return;
        }

        let objectUrl = "";

        const revokeObjectUrl = () => {
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                objectUrl = "";
            }
        };

        const clearPreview = () => {
            revokeObjectUrl();
            image.removeAttribute("src");
            image.hidden = true;
            video.pause();
            video.removeAttribute("src");
            video.load();
            video.hidden = true;
            preview.hidden = true;
        };

        const selectedMediaKind = (file) => {
            if (file.type.startsWith("image/")) {
                return "image";
            }
            if (file.type.startsWith("video/")) {
                return "short_video";
            }
            return mediaTypeInput ? mediaTypeInput.value : "";
        };

        const showSelectedFile = () => {
            clearPreview();
            const [file] = fileInput.files;
            if (!file) {
                return;
            }

            const kind = selectedMediaKind(file);
            if (kind !== "image" && kind !== "short_video") {
                return;
            }

            objectUrl = URL.createObjectURL(file);
            if (kind === "image") {
                image.src = objectUrl;
                image.hidden = false;
            } else {
                video.src = objectUrl;
                video.hidden = false;
                video.load();
            }
            preview.hidden = false;
        };

        fileInput.addEventListener("change", showSelectedFile);
        removeButton.addEventListener("click", () => {
            clearPreview();
            fileInput.value = "";
            fileInput.focus();
        });
        window.addEventListener("pagehide", revokeObjectUrl, { once: true });
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeUploadPreview, { once: true });
    } else {
        initializeUploadPreview();
    }
})();
