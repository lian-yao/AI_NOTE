// React 19 + TypeScript 5.7+ 兼容补丁
// 老库（recharts、shikijs、rehype-react）引用了全局 JSX 命名空间
// React 19 已移除该命名空间，需要手动补回

import 'react';

declare global {
  namespace JSX {
    type Element = React.ReactElement;
    type IntrinsicElements = React.JSX.IntrinsicElements;
  }
}
