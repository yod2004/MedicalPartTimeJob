int xPin = A0;
int yPin = A1;
int zPin = A2;

void setup() {
  pinMode(xPin,INPUT);
  pinMode(yPin,INPUT);
  pinMode(zPin,INPUT);
  Serial.begin(9600);
}

void loop() {
  Serial.print(0);
  Serial.print(" ");

  Serial.print(analogRead(xPin));
  Serial.print(" ");
  Serial.print(analogRead(yPin));
  Serial.print(" ");
  Serial.print(analogRead(zPin));
  
  Serial.print(" ");
  Serial.println(400);
}
