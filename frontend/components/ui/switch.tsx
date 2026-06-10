'use client'
import * as React from 'react'
import { cn } from '@/lib/utils'

interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string
}

export const Switch = React.forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, label, id, ...props }, ref) => {
    return (
      <label htmlFor={id} className="flex cursor-pointer items-center gap-2">
        <div className="relative">
          <input id={id} type="checkbox" ref={ref} className="sr-only" {...props} />
          <div className={cn(
            'h-6 w-11 rounded-full transition-colors',
            props.checked ? 'bg-blue-600' : 'bg-gray-300',
            className,
          )} />
          <div className={cn(
            'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform',
            props.checked ? 'translate-x-5' : 'translate-x-0.5',
          )} />
        </div>
        {label && <span className="text-sm text-gray-700">{label}</span>}
      </label>
    )
  }
)
Switch.displayName = 'Switch'
