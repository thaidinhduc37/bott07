import { useId } from 'react';

type NativeInput = React.InputHTMLAttributes<HTMLInputElement>;
type NativeTextarea = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

/**
 * Thuộc tính riêng của component, tách khỏi thuộc tính DOM.
 *
 * Ô nhập và ô nhiều dòng dùng chung phần lớn thuộc tính (value, onChange,
 * placeholder, disabled, required). Giao nhau hai kiểu native cho `never` ở
 * những chỗ chúng khác nhau, nên chỉ nhận phần chung rồi ép kiểu một lần khi
 * truyền xuống phần tử thật.
 */
type CommonNative = Omit<NativeInput, 'className' | 'id'> & Omit<NativeTextarea, 'className' | 'id'>;

interface FieldProps extends Pick<
  CommonNative,
  'name' | 'value' | 'onChange' | 'onBlur' | 'placeholder' | 'disabled' | 'required' | 'readOnly' | 'autoComplete' | 'maxLength' | 'inputMode'
> {
  label: string;
  hint?: string;
  error?: string;
  /** Chỉ dùng cho `as="input"`. */
  type?: NativeInput['type'];
  as?: 'input' | 'textarea';
  rows?: number;
  /**
   * Trường được hệ thống lấy sẵn từ hồ sơ. Khóa lại và nói rõ lấy từ đâu —
   * người dùng gặp một ô không gõ được mà không có lời giải thích sẽ tưởng là lỗi.
   */
  autofilledFrom?: string;
}

export function Field({
  label,
  hint,
  error,
  required,
  autofilledFrom,
  as = 'input',
  type = 'text',
  rows,
  ...rest
}: FieldProps) {
  const id = useId();
  const describedBy = [hint && !error ? `${id}-hint` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(' ');

  const wrapperClass = ['field', error ? 'field--invalid' : '', autofilledFrom ? 'field--autofilled' : '']
    .filter(Boolean)
    .join(' ');

  const shared = {
    id,
    className: 'field__input',
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy || undefined,
    required,
    ...rest,
  };

  return (
    <div className={wrapperClass}>
      <label className="field__label" htmlFor={id}>
        {label}
        {required && (
          <span className="req" aria-hidden="true">
            *
          </span>
        )}
        {autofilledFrom && <span className="field__locked">↳ lấy từ {autofilledFrom}</span>}
      </label>

      {as === 'textarea' ? (
        <textarea rows={rows} {...(shared as NativeTextarea)} />
      ) : (
        <input type={type} {...(shared as NativeInput)} />
      )}

      {hint && !error && (
        <span className="field__hint" id={`${id}-hint`}>
          {hint}
        </span>
      )}
      {error && (
        <span className="field__error" id={`${id}-error`} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
