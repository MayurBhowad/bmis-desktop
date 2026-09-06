import { useState } from 'react';
import './App.css'
import { invoke } from '@tauri-apps/api/core';

function App() {
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const pingPython = async () => {
    setLoading(true);

    try {
      const response = await invoke<string>('python_ping');
      setMessage(response);
    } catch (error) {
      setMessage(`Error: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <h1>BMis Desktop</h1>

      <button onClick={pingPython} disabled={loading}>{loading ? 'Pinging...' : 'Ping Python'}</button>

      {message && <p>{message}</p>}
    </main>
  );
}

export default App
