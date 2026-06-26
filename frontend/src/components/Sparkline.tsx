import React from "react";
import { View } from "react-native";
import Svg, { Path } from "react-native-svg";

type Props = {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  strokeWidth?: number;
};

export default function Sparkline({
  data,
  width = 72,
  height = 28,
  color = "#3F6156",
  strokeWidth = 1.5,
}: Props) {
  if (!data || data.length < 2) {
    return <View style={{ width, height }} />;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = Math.max(max - min, 1e-9);
  const stepX = data.length > 1 ? width / (data.length - 1) : width;
  const pts = data
    .map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / span) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <Svg width={width} height={height}>
      <Path d={pts} stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  );
}
