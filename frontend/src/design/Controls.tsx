import { useId } from 'react'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'

interface SliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  unit?: string
  onChange: (v: number) => void
}

export function LabeledSlider({ label, value, min, max, step, unit, onChange }: SliderProps) {
  const id = useId()
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <label id={id} className="text-sm">{label}</label>
        <span className="font-mono text-sm tabular-nums text-cyan">
          {value}
          {unit && <span className="ml-0.5 text-xs text-text2">{unit}</span>}
        </span>
      </div>
      <Slider
        aria-labelledby={id}
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={(v) => onChange(Array.isArray(v) ? (v[0] ?? value) : v)}
      />
    </div>
  )
}

export function LabeledSwitch({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm">{label}</span>
      <Switch aria-label={label} checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

export function NumberField({ label, value, onChange, step = 0.1, unit }: { label: string; value: number; onChange: (v: number) => void; step?: number; unit?: string }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="w-14 text-text2">{label}</span>
      <input
        type="number"
        aria-label={`${label} frequency`}
        value={value}
        step={step}
        min={1}
        max={40}
        onChange={(e) => {
          const v = Number(e.target.value)
          if (Number.isFinite(v)) onChange(v)
        }}
        className="w-20 rounded-md border border-white/12 bg-white/5 px-2 py-1 font-mono text-sm tabular-nums outline-none focus:border-cyan"
      />
      {unit && <span className="text-xs text-text2">{unit}</span>}
    </label>
  )
}
