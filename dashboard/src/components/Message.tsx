export function Message({ error }: Readonly<{ error?: Error }>) {
  return (
    <p className="message" role={error ? "alert" : "status"}>
      {error ? error.message : "Loading..."}
    </p>
  );
}
