const uint8_t Power_Control_Pin = A15; // Define power control pins
// Define motor control pins
const uint8_t Motor_Control_Pin[49] = {
   1,2, 3, 4, 5, 6, 7,
  8, 9, 10, 11,12 , 13,
  14, 15, 16, 17, 18, 19,
  22, 23, 24, 25, 26, 27, 
  A0, A1, A2, A3, A4,
  A5, A6, A7, A8,A9 , A10,
  A11, A12, A13, A14, 35, 36,
  37, 38, 39, 40, 41, 42, 43
};
// Define feedback  pins
//const uint8_t Feedback_Sensor_Pin[24] = {
  //12, 10, 8, 6, 4, 2,
 //15, 17, 19, 23, 25, 27,
  //31, 33, 35, 37, 39, 41,
 // 43, 45, 47, 49, 51, 53
//};
uint8_t pinValue = 0;     // Store Pin value
uint8_t pulseValue = 0;   // Store impulse value
uint16_t cmdValue = 0;    // Store command value
uint8_t rxCount = 0;      // Used for serial port receiving count
char rxBuffer[200] = {0}; // Store data received by serial port
void setup()
{
  Serial.begin(115200);                   // Initialize serial port, baud rate 9600
  pinMode(Power_Control_Pin, OUTPUT);   // Set the power control pin to output mode
  digitalWrite(Power_Control_Pin, LOW); // Set the power control pin output low level
  for (uint8_t i = 0; i < 49; i++)      // 
  {
    pinMode(Motor_Control_Pin[i], OUTPUT);         // Set the motor control pin to output mode
    digitalWrite(Motor_Control_Pin[i], HIGH);       // Set the motor control pin output low level
   // pinMode(Feedback_Sensor_Pin[i], INPUT_PULLUP); // Set the feedback pin to the pull-up input mode
  }
}

void loop()
{
  while (Serial.available()) // Cycle until no data is readable on the serial port
  {
    rxBuffer[rxCount] = Serial.read(); // Read one bit data
    if (rxBuffer[rxCount] == '\n')     // If the terminator is received
    {
      rxBuffer[rxCount] = 0;    // Set packet Terminator
      Serial.println(rxBuffer); // Print received data
      Unpack_Data();            // Parse data
      rxCount = 0;              // Restart receiving data
    }
    else                //
      rxCount++;      // 
    if (rxCount >= 200) // If the received data exceeds the size of the serial port buffer array
      rxCount = 0;    // Restart receiving
  }
}
void Unpack_Data(void)
{
  char *Tail = NULL, *Head = NULL;            // Pointer to store parsing data
  if ((Head = strchr(rxBuffer, 'M')) != NULL) // If M is found
  {
    if ((Tail = strchr(Head, ' ')) != NULL) //If a space character is found
    {
      *Tail = 0;                 //Truncate string
      cmdValue = atoi(Head + 1); // 
      Serial.print(cmdValue);    // 
      Serial.print(",");         // 
      if (cmdValue == 610)       // 610
      {
        if (strstr(Tail + 1, "S1") != NULL) // If S1 is searched
        {
          digitalWrite(Power_Control_Pin, HIGH); // Power on
          Serial.print(1);                       //
        }
        else if (strstr(Tail + 1, "S0") != NULL) // If S0 is searched
        {
          digitalWrite(Power_Control_Pin, LOW); // Turn off the power
          Serial.print(0);                      // 
        }
      }
      else if (cmdValue == 600) // 600
      {
        Head = strchr(Tail + 1, 'N');             // Find N
        Tail = strchr(Head, ' ');                 // Find spaces
        *Tail = 0;                                // Truncate string
        pinValue = atoi(Head + 1);                // Get pin number
        //Head = strchr(Tail + 1, 'F');             // Find F
        //pulseValue = atoi(Head + 1);              // Get propulsion value
        //pulseValue = pulseValue / 4;              // Convert to pulse number (4mm, 8mm, 12mm, 16mm, 24mm, using 1:30 reduction ratio turbine. Turn the vortex rod once, the gear advances 4mm,
                                                  //turn it twice, advances 8mm, and so on
        pulseValue =1;          // Convert to pulse number (2mm, using a 1:60 reduction ratio turbine. The scroll rod rotates once, and the gear advances 2mm)
        Serial.print(pinValue);                   // 
        Serial.print(",");                        // 
        Serial.print(pulseValue);                 // 
        Send_Pulse();                             // Send pulse
      }
      Serial.println(); // 打印调试信息
    }
  }
}
void Send_Pulse(void)
{
    digitalWrite(Motor_Control_Pin[pinValue], LOW);          // Motor control pin output high level     delay(10);                                                 //Wait for 300ms
    delay(10);  
    digitalWrite(Motor_Control_Pin[pinValue], HIGH);           // Motor control pin output low level 
    //while (digitalRead(Feedback_Sensor_Pin[pinValue]) != HIGH);    // Cycle until the feedback pin is low level
   
  
}
