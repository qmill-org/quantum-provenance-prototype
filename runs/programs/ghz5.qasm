OPENQASM 3.0;
qubit[5] q;
bit[5] c;
h q[0];
cnot q[0], q[1];
cnot q[1], q[2];
cnot q[2], q[3];
cnot q[3], q[4];
c = measure q;
