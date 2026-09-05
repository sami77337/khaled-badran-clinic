(function () {
    "use strict";

    const recorderRoot = document.querySelector("[data-consultation-audio-recorder]");
    const replyForm = document.querySelector("[data-consultation-reply-form]");
    if (!recorderRoot || !replyForm) {
        return;
    }

    const audioInput = recorderRoot.querySelector("[data-consultation-audio-input]");
    const removeInput = recorderRoot.querySelector("input[name='remove_audio']");
    const startButton = recorderRoot.querySelector("[data-audio-start]");
    const stopButton = recorderRoot.querySelector("[data-audio-stop]");
    const listenButton = recorderRoot.querySelector("[data-audio-listen]");
    const recordAgainButton = recorderRoot.querySelector("[data-audio-record-again]");
    const removeButton = recorderRoot.querySelector("[data-audio-remove]");
    const timerOutput = recorderRoot.querySelector("[data-audio-timer]");
    const statusOutput = recorderRoot.querySelector("[data-audio-status]");
    const localPreview = recorderRoot.querySelector("[data-audio-local-preview]");
    const existingPreview = recorderRoot.querySelector("[data-audio-existing-preview]");

    const maxDurationSeconds = Number(recorderRoot.dataset.maxDurationSeconds || 300);
    const maxSizeBytes = Number(audioInput.dataset.maxSizeBytes || 15 * 1024 * 1024);
    const hasExistingAudio = recorderRoot.dataset.hasExistingAudio === "true";
    const formatOptions = [
        { mimeType: "audio/webm;codecs=opus", contentType: "audio/webm", extension: ".webm" },
        { mimeType: "audio/ogg;codecs=opus", contentType: "audio/ogg", extension: ".ogg" },
        { mimeType: "audio/mp4", contentType: "audio/mp4", extension: ".m4a" },
        { mimeType: "audio/webm", contentType: "audio/webm", extension: ".webm" },
        { mimeType: "audio/ogg", contentType: "audio/ogg", extension: ".ogg" },
    ];

    let mediaRecorder = null;
    let mediaStream = null;
    let recordedChunks = [];
    let pendingObjectUrl = "";
    let pendingRecording = false;
    let existingRemovalPending = false;
    let recordingStartedAt = 0;
    let timerIntervalId = null;
    let autoStopTimeoutId = null;
    let autoStopped = false;
    let submitAfterStop = false;
    let pendingSubmitter = null;

    const recordingSupported = Boolean(
        window.MediaRecorder
        && navigator.mediaDevices
        && typeof navigator.mediaDevices.getUserMedia === "function"
        && window.DataTransfer
        && window.File
    );

    function setStatus(message) {
        statusOutput.textContent = message || "";
    }

    function formatDuration(seconds) {
        const safeSeconds = Math.max(0, Math.min(maxDurationSeconds, Math.floor(seconds)));
        const minutes = String(Math.floor(safeSeconds / 60)).padStart(2, "0");
        const remainder = String(safeSeconds % 60).padStart(2, "0");
        return `${minutes}:${remainder}`;
    }

    function updateTimer() {
        if (!recordingStartedAt) {
            timerOutput.textContent = "00:00";
            return;
        }
        const elapsedSeconds = (Date.now() - recordingStartedAt) / 1000;
        timerOutput.textContent = formatDuration(elapsedSeconds);
    }

    function stopPreview(audioElement) {
        if (audioElement && !audioElement.paused) {
            audioElement.pause();
        }
    }

    function activePreview() {
        if (pendingRecording && !localPreview.hidden) {
            return localPreview;
        }
        if (hasExistingAudio && !existingRemovalPending && existingPreview && !existingPreview.hidden) {
            return existingPreview;
        }
        return null;
    }

    function updateButtons() {
        const recording = Boolean(mediaRecorder && mediaRecorder.state === "recording");
        const preview = activePreview();
        startButton.disabled = recording || !recordingSupported;
        stopButton.disabled = !recording;
        listenButton.disabled = recording || !preview;
        recordAgainButton.disabled = recording || !recordingSupported || !preview;
        removeButton.disabled = recording || (!pendingRecording && (!hasExistingAudio || existingRemovalPending));
    }

    function stopMicrophone() {
        if (mediaStream) {
            mediaStream.getTracks().forEach(function (track) {
                track.stop();
            });
        }
        mediaStream = null;
    }

    function clearRecordingTimers() {
        if (timerIntervalId !== null) {
            window.clearInterval(timerIntervalId);
            timerIntervalId = null;
        }
        if (autoStopTimeoutId !== null) {
            window.clearTimeout(autoStopTimeoutId);
            autoStopTimeoutId = null;
        }
    }

    function clearPendingRecording() {
        stopPreview(localPreview);
        if (pendingObjectUrl) {
            URL.revokeObjectURL(pendingObjectUrl);
            pendingObjectUrl = "";
        }
        localPreview.removeAttribute("src");
        localPreview.load();
        localPreview.hidden = true;
        audioInput.value = "";
        pendingRecording = false;
    }

    function normalizedContentType(value) {
        return String(value || "").split(";", 1)[0].trim().toLowerCase();
    }

    function formatForContentType(contentType) {
        return formatOptions.find(function (option) {
            return option.contentType === contentType;
        });
    }

    function createRecorder(stream) {
        for (const option of formatOptions) {
            if (
                typeof MediaRecorder.isTypeSupported === "function"
                && !MediaRecorder.isTypeSupported(option.mimeType)
            ) {
                continue;
            }
            try {
                return new MediaRecorder(stream, { mimeType: option.mimeType });
            } catch (error) {
                // Continue through the browser-recording formats allowed by the server.
            }
        }

        try {
            const defaultRecorder = new MediaRecorder(stream);
            if (formatForContentType(normalizedContentType(defaultRecorder.mimeType))) {
                return defaultRecorder;
            }
        } catch (error) {
            // The localized unsupported-format status below is sufficient for the user.
        }
        throw new Error("unsupported-audio-format");
    }

    function attachRecording(blob, contentType, extension) {
        if (!blob.size) {
            throw new Error("empty-audio");
        }
        if (blob.size > maxSizeBytes) {
            throw new Error("audio-too-large");
        }

        const filename = `consultation-reply-${Date.now()}${extension}`;
        const recordedFile = new File([blob], filename, { type: contentType });
        const transfer = new DataTransfer();
        transfer.items.add(recordedFile);
        audioInput.files = transfer.files;

        pendingObjectUrl = URL.createObjectURL(blob);
        localPreview.src = pendingObjectUrl;
        localPreview.hidden = false;
        localPreview.load();
        if (existingPreview) {
            existingPreview.hidden = true;
        }
        removeInput.value = "";
        existingRemovalPending = false;
        pendingRecording = true;
    }

    function finishRecording() {
        clearRecordingTimers();
        stopMicrophone();
        recordingStartedAt = 0;
        timerOutput.textContent = autoStopped ? formatDuration(maxDurationSeconds) : timerOutput.textContent;

        const detectedContentType = normalizedContentType(
            (mediaRecorder && mediaRecorder.mimeType)
            || (recordedChunks[0] && recordedChunks[0].type)
        );
        const selectedFormat = formatForContentType(detectedContentType);

        try {
            if (!selectedFormat) {
                throw new Error("unsupported-audio-format");
            }
            const blob = new Blob(recordedChunks, { type: detectedContentType });
            attachRecording(blob, selectedFormat.contentType, selectedFormat.extension);
            setStatus(
                autoStopped
                    ? `${recorderRoot.dataset.maxTimeMessage} ${recorderRoot.dataset.readyMessage}`
                    : recorderRoot.dataset.readyMessage
            );
        } catch (error) {
            clearPendingRecording();
            if (existingPreview && !existingRemovalPending) {
                existingPreview.hidden = false;
            }
            if (error.message === "audio-too-large") {
                setStatus(recorderRoot.dataset.sizeMessage);
            } else if (error.message === "empty-audio") {
                setStatus(recorderRoot.dataset.emptyMessage);
            } else {
                setStatus(recorderRoot.dataset.formatMessage);
            }
            submitAfterStop = false;
            pendingSubmitter = null;
        }

        recordedChunks = [];
        mediaRecorder = null;
        updateButtons();

        if (submitAfterStop) {
            submitAfterStop = false;
            const submitter = pendingSubmitter;
            pendingSubmitter = null;
            if (submitter) {
                replyForm.requestSubmit(submitter);
            } else {
                replyForm.requestSubmit();
            }
        }
    }

    async function startRecording() {
        if (!recordingSupported || (mediaRecorder && mediaRecorder.state === "recording")) {
            return;
        }

        clearPendingRecording();
        stopPreview(existingPreview);
        removeInput.value = "";
        existingRemovalPending = false;
        if (existingPreview) {
            existingPreview.hidden = false;
        }
        setStatus("");
        timerOutput.textContent = "00:00";

        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = createRecorder(mediaStream);
        } catch (error) {
            stopMicrophone();
            mediaRecorder = null;
            setStatus(
                error.message === "unsupported-audio-format"
                    ? recorderRoot.dataset.formatMessage
                    : recorderRoot.dataset.permissionMessage
            );
            updateButtons();
            return;
        }

        recordedChunks = [];
        autoStopped = false;
        mediaRecorder.addEventListener("dataavailable", function (event) {
            if (event.data && event.data.size > 0) {
                recordedChunks.push(event.data);
            }
        });
        mediaRecorder.addEventListener("stop", finishRecording, { once: true });
        mediaRecorder.addEventListener("error", function () {
            setStatus(recorderRoot.dataset.emptyMessage);
        }, { once: true });
        mediaRecorder.start(1000);
        recordingStartedAt = Date.now();
        updateTimer();
        timerIntervalId = window.setInterval(updateTimer, 250);
        autoStopTimeoutId = window.setTimeout(function () {
            autoStopped = true;
            stopRecording();
        }, maxDurationSeconds * 1000);
        updateButtons();
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            updateTimer();
            mediaRecorder.stop();
            clearRecordingTimers();
            stopButton.disabled = true;
        }
    }

    startButton.addEventListener("click", startRecording);
    stopButton.addEventListener("click", stopRecording);
    recordAgainButton.addEventListener("click", startRecording);

    listenButton.addEventListener("click", function () {
        const preview = activePreview();
        if (preview) {
            preview.play().catch(function () {
                setStatus(recorderRoot.dataset.emptyMessage);
            });
        }
    });

    removeButton.addEventListener("click", function () {
        if (pendingRecording) {
            clearPendingRecording();
            if (existingPreview && !existingRemovalPending) {
                existingPreview.hidden = false;
            }
            setStatus("");
        } else if (hasExistingAudio && existingPreview) {
            stopPreview(existingPreview);
            existingPreview.hidden = true;
            removeInput.value = "on";
            existingRemovalPending = true;
            setStatus(recorderRoot.dataset.removedMessage);
        }
        updateButtons();
    });

    replyForm.addEventListener("submit", function (event) {
        if (mediaRecorder && mediaRecorder.state === "recording") {
            event.preventDefault();
            submitAfterStop = true;
            pendingSubmitter = event.submitter || null;
            stopRecording();
        }
    });

    window.addEventListener("beforeunload", function () {
        clearRecordingTimers();
        stopMicrophone();
        if (pendingObjectUrl) {
            URL.revokeObjectURL(pendingObjectUrl);
        }
    });

    if (!recordingSupported) {
        setStatus(recorderRoot.dataset.unsupportedMessage);
    }
    updateButtons();
})();
