export default function CityField({ value, onChange }) {
  return (
    <label className="city-field">
      <span>城市</span>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete="off"
        spellCheck="false"
      />
    </label>
  );
}
