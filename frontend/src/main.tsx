import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { MotionConfig } from 'framer-motion';
import { ThemeProvider } from './components/ThemeProvider';
import { DensityProvider } from './components/DensityProvider';
import { ConfirmProvider } from './components/ConfirmDialog';
import ErrorBoundary from './components/ErrorBoundary';
import AuthInit from './components/AuthInit';
import { queryClient } from './api/queryClient';
import App from './App';
import './styles/index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ThemeProvider>
            <DensityProvider>
              <ConfirmProvider>
                <AuthInit>
                  <BrowserRouter>
                    <App />
                  </BrowserRouter>
                </AuthInit>
              </ConfirmProvider>
            </DensityProvider>
          </ThemeProvider>
        </QueryClientProvider>
      </ErrorBoundary>
    </MotionConfig>
  </React.StrictMode>,
);
