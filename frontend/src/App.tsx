import { useState } from 'react';
import './App.css'
import { invoke } from '@tauri-apps/api/core';

function App() {
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);

  const sendPing = async () => {
    setLoading(true);
    try {
      const result = await invoke<string>('python_request', { request: JSON.stringify({ command: 'ping' }) });
      setResponse(result);
    } catch (error) {
      setResponse(`Error: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <h1>BMis Desktop</h1>

      <button onClick={sendPing} disabled={loading}>{loading ? 'Pinging...' : 'Ping Python'}</button>

      {response && <p>{response}</p>}
    </main>
  );
}

export default App
