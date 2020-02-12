carWidth = 160
carHeight = 240
chessboardSize = 80
shiftWidth = 120
shiftHeight = 120
innerShiftWidth = 0
innerShiftHeight = 0
totalWidth = carWidth + 2 * chessboardSize + 2 * shiftWidth
totalHeight = carHeight + 2 * chessboardSize + 2 * shiftHeight

x1 = shiftWidth + chessboardSize + innerShiftWidth
x2 = totalWidth - x1
y1 = shiftHeight + chessboardSize + innerShiftHeight
y2 = totalHeight - y1

frontShape = (totalWidth, y1)
leftShape = (totalHeight, x1)
