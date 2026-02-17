"use strict";
/// <reference lib="webworker" />
/// <reference lib="dom" />
class RecorderWorkletProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super();
        this.bufferSize = options?.processorOptions?.bufferSize || 4096;
        this.buffer = new Float32Array(this.bufferSize);
        this.currentBufferPosition = 0;
    }
    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const channelData = input[0];
            if (channelData) {
                const remainingSpace = this.bufferSize - this.currentBufferPosition;
                const dataToCopy = Math.min(channelData.length, remainingSpace);
                this.buffer.set(channelData.subarray(0, dataToCopy), this.currentBufferPosition);
                this.currentBufferPosition += dataToCopy;
                if (this.currentBufferPosition >= this.bufferSize) {
                    // Buffer is full, post it back to the main thread
                    this.port.postMessage(this.buffer);
                    // Reset buffer
                    this.buffer = new Float32Array(this.bufferSize);
                    // Handle any leftover data
                    const leftoverData = channelData.subarray(dataToCopy);
                    if (leftoverData.length > 0) {
                        this.buffer.set(leftoverData, 0);
                        this.currentBufferPosition = leftoverData.length;
                    }
                    else {
                        this.currentBufferPosition = 0;
                    }
                }
            }
        }
        return true; // Keep processor alive
    }
}
registerProcessor('recorder-worklet-processor', RecorderWorkletProcessor);
