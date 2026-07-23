import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from './components/ThemeProvider';
import { ConfirmProvider } from './components/ConfirmDialog';
import AuthInit from './components/AuthInit';
import App from './App';
import './styles/index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <ConfirmProvider>
        <AuthInit>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AuthInit>
      </ConfirmProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
