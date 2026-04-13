import { ButtonHTMLAttributes, forwardRef } from 'react'
import { clsx } from 'clsx'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={clsx(
          'inline-flex items-center justify-center font-semibold rounded-lg transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed',
          {
            'bg-[#060B4E] text-white hover:bg-[#0a1065]': variant === 'primary',
            'bg-[#F1F5F9] text-[#060B4E] border border-[#E2E8F2] hover:bg-[#E2E8F2]': variant === 'secondary',
            'bg-[#FFF5F5] text-red-600 border border-red-200 hover:bg-red-50': variant === 'danger',
            'bg-transparent text-[#64748B] hover:bg-[#F1F5F9]': variant === 'ghost',
          },
          {
            'text-xs px-3 py-1.5': size === 'sm',
            'text-sm px-4 py-2': size === 'md',
            'text-base px-6 py-3': size === 'lg',
          },
          className
        )}
        {...props}
      >
        {children}
      </button>
    )
  }
)

Button.displayName = 'Button'
