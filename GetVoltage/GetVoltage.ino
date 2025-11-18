int voltagePin = A2;
float voltage = 0;

float fmap(float x, float in_min, float in_max, float out_min, float out_max){
    float x_new = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
    return x_new;
}

void setup() {
  // put your setup code here, to run once:
  Serial.begin(2000000);
}

void loop() {
  // put your main code here, to run repeatedly:
  voltage = fmap(analogRead(voltagePin), 0.0, 1023.0, 0.0, 29.0);
  // Serial.print(0);Serial.print(" ");
  Serial.println(voltage);
  // Serial.print(" ");Serial.println(25);
}
