// Compact symbol input backed by a datalist of all symbols + names.
export default function SymbolPicker({ symbols, value, onChange }) {
  return (
    <>
      <input
        list="symbol-list"
        value={value}
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        style={{ width: 120, textTransform: "uppercase" }}
        placeholder="代码"
      />
      <datalist id="symbol-list">
        {symbols.map((s) => (
          <option key={s.symbol} value={s.symbol}>
            {s.name}
          </option>
        ))}
      </datalist>
    </>
  );
}
