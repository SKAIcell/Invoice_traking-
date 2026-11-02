
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/global.css';
import './styles/login.css';
import './styles/dashboard.css';
import './styles/invoices.css';
import "./styles/orders.css";
import "./styles/budgets.css";
import './styles/layout.css';
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
