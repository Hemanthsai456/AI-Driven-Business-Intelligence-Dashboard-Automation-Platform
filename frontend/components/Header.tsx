'use client';

import React from 'react';
import { TopBar } from './TopBar';

interface HeaderProps {
  datasetName?: string;
  sourceType?: string;
  rowCount?: number;
  columnCount?: number;
}

export const Header: React.FC<HeaderProps> = (props) => {
  return <TopBar {...props} />;
};
