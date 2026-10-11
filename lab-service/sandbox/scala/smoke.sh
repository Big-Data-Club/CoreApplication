#!/bin/sh
set -eu
mkdir -p /tmp/work/classes
cat > /tmp/work/Main.scala <<'SCALA'
object Main {
  def main(args: Array[String]): Unit = {
    val nums = scala.io.StdIn.readLine().split(" ").map(_.toInt)
    println(nums.zipWithIndex.filter { case (_, i) => nums.length % (i + 1) == 0 }.map { case (n, _) => n * n }.sum)
  }
}
SCALA
scalac -d /tmp/work/classes /tmp/work/Main.scala
test "$(printf '1 2 3 4\n' | scala -cp /tmp/work/classes Main)" = 21
test "$(printf '2 7 1 19 18 3\n' | scala -cp /tmp/work/classes Main)" = 63

echo "Scala compile and both sample cases passed"
