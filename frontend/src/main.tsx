import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from './components/ThemeProvider';
import { ConfirmProvider } from './components/ConfirmDialog';
import ErrorBoundary from './components/ErrorBoundary';
import AuthInit from './components/AuthInit';
import App from './App';
import './styles/index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <ConfirmProvider>
          <AuthInit>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AuthInit>
        </ConfirmProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
