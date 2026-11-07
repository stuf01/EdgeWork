type FieldLabelProps = {
  text: string;
  tip: string;
};

export function FieldLabel({ text, tip }: FieldLabelProps) {
  return (
    <span className="field-label">
      {text}
      <span className="tip" tabIndex={0} aria-label={tip}>
        <span className="tip-mark" aria-hidden="true">
          ?
        </span>
        <span className="tip-bubble" role="tooltip">
          {tip}
        </span>
      </span>
    </span>
  );
}
