import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// The only two charts that need the chart library. They load on their own, so the library never delays the first screen.

export function HistogramChart({ data }: { data: { value: number; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={84}>
      <BarChart data={data} margin={{ top: 4, right: 14, bottom: 0, left: 14 }} barCategoryGap={0}>
        <XAxis dataKey="value" tick={{ fontSize: 10, fill: '#8e9c97' }} tickLine={false} axisLine={false} interval={12} />
        <Tooltip cursor={{ fill: 'rgba(255,255,255,.06)' }} contentStyle={{ background: '#18232a', border: '1px solid rgba(255,255,255,.12)', borderRadius: 8, fontSize: 12 }} formatter={(v) => [Number(v).toLocaleString(), 'pixels']} labelFormatter={(v) => `from ${v}`} />
        <Bar dataKey="count" fill="#5fe0c9" isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DayLineChart({ data, name }: { data: { time: string; value: number | null }[]; name: string }) {
  return (
    <ResponsiveContainer width="100%" height={110}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid stroke="#2c383f" vertical={false} />
        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ba8a3' }} tickLine={false} axisLine={false} />
        <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#9ba8a3' }} tickLine={false} axisLine={false} width={46} />
        <Tooltip contentStyle={{ background: '#182025', border: '1px solid #33404a', fontSize: 12 }} formatter={(v) => [Number(v).toFixed(2), name]} labelFormatter={(v) => `${v}:00 UTC`} />
        <Line type="monotone" dataKey="value" stroke="#7fd1c7" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
