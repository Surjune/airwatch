import { ImageUp, X } from 'lucide-react';
import { useEffect, useId, useState } from 'react';

interface PhotoDropzoneProps {
  readonly file: File | null;
  readonly onChange: (file: File | null) => void;
}

/**
 * Choose a photograph by click or drop, with a preview of what will be sent.
 *
 * The preview matters more than it looks: the most common refusal is a frame
 * with nothing distant in it, and seeing the image before submitting catches
 * that without a round trip.
 */
export function PhotoDropzone({ file, onChange }: PhotoDropzoneProps) {
  const inputId = useId();
  const [isDragging, setIsDragging] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [file]);

  if (file && preview) {
    return (
      <div className="relative overflow-hidden rounded-sm border border-border bg-surface-sunken">
        <img
          src={preview}
          alt="The photograph to submit"
          className="max-h-72 w-full object-contain"
        />
        <div className="flex items-center justify-between gap-3 border-t border-border bg-surface px-3 py-2">
          <span className="min-w-0 truncate text-xs text-ink-muted">
            {file.name} · {(file.size / 1024 / 1024).toFixed(1)} MB
          </span>
          <button
            type="button"
            onClick={() => {
              onChange(null);
            }}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-ink-muted hover:bg-surface-sunken hover:text-ink"
          >
            <X aria-hidden className="size-3.5" />
            Remove
          </button>
        </div>
      </div>
    );
  }

  return (
    <label
      htmlFor={inputId}
      onDragOver={(event) => {
        event.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => {
        setIsDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        const dropped = event.dataTransfer.files[0];
        if (dropped?.type.startsWith('image/')) onChange(dropped);
      }}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-sm border border-dashed px-6 py-9 text-center transition-colors ${
        isDragging
          ? 'border-ink bg-surface-sunken'
          : 'border-border-strong bg-paper hover:border-ink/60'
      }`}
    >
      <ImageUp aria-hidden className="size-6 text-ink-muted" strokeWidth={1.6} />
      <span className="mt-3 text-sm font-medium text-ink">
        <span className="sm:hidden">Take or choose a photograph</span>
        <span className="hidden sm:inline">
          Drop a photograph here, or{' '}
          <span className="underline decoration-ink/30 underline-offset-4">browse</span>
        </span>
      </span>
      <span className="mt-1 text-xs text-ink-subtle">JPEG or PNG, up to 10 MB</span>
      <input
        id={inputId}
        type="file"
        accept="image/*"
        className="sr-only"
        onChange={(event) => {
          onChange(event.target.files?.[0] ?? null);
        }}
      />
    </label>
  );
}
