@echo off
chcp 65001
mvn exec:java -Dexec.args="--message \"你能掷一个 12 面的骰子并检查结果是否为素数吗?\""