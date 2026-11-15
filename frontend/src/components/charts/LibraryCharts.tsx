import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// The only two charts that need the chart library. They load on their own, so the library never delays the first screen.

export function HistogramChart({ data }: { data: { value: number; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={84}>
      <BarChart data={data} margin={{ top: 4, right: 14, bottom: 0, left: 14 }} barCategoryGap={0}>
        <XAxis dataKey="value" tick={{ fontSize: 10, fill: '#bdb7da' }} tickLine={false} axisLine={false} interval={12} />
        <Tooltip cursor={{ fill: 'rgba(255,255,255,.06)' }} contentStyle={{ background: '#24164a', border: '1px solid rgba(255,255,255,.32)', borderRadius: 14, fontSize: 12 }} formatter={(v) => [Number(v).toLocaleString(), 'pixels']} labelFormatter={(v) => `from ${v}`} />
        <Bar dataKey="count" fill="#c3ccff" isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DayLineChart({ data, name }: { data: { time: string; value: number | null }[]; name: string }) {
  return (
    <ResponsiveContainer width="100%" height={110}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="rgba(255,255,255,.14)" vertical={false} />
        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#bdb7da' }} tickLine={false} axisLine={false} />
        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#bdb7da' }} tickLine={false} axisLine={false} width={46} />
        <Tooltip contentStyle={{ background: '#24164a', border: '1px solid rgba(255,255,255,.32)', borderRadius: 14, fontSize: 12 }} formatter={(v) => [Number(v).toFixed(2), name]} labelFormatter={(v) => `${v}:00 UTC`} />
        <Line type="monotone" dataKey="value" stroke="#c3ccff" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
