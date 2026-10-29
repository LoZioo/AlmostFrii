#include <stdio.h>
#include "pico/stdlib.h"
#include "stdlib.h"
#include <math.h>
#include <string.h>
#include "tusb.h"

#ifdef PICO_W_BOARD
    #include "pico/cyw43_arch.h"
#else
    #define LED_PIN 25 
#endif


#include "commands.h"


void toggle_LED(bool value)
{
#ifdef PICO_W_BOARD
    // Pico W uses the CYW43 WiFi chip LED
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, value);
#else
    // Regular Pico uses GPIO LED
    gpio_put(LED_PIN, value);
#endif
}


u8 str[100] = {0};
u8 str_idx = 0;


bool marker_found(char *marker) {
    int pos = 0;  
    for(int i = 0 ; i < str_idx; ++i){
    char c= str[i];

    if (c == -1) return false;  
    if (c == marker[pos]) {
        pos++;
       // putchar(pos+'0');                     
        if (marker[pos] == '\0') {  
            pos = 0;                
            return true;           

        }
    } else if (c == marker[0]) {
        pos = 1;       
    } else {
        pos = 0;        
    }
    }
    return false;
}

inline bool addr_to_u32(int start_idx, int end_idx, u32 *addr) {

        *addr = 0;
        for (int i = start_idx + 1; i < end_idx; i++) {
        char c = str[i];

        u8 value;
        if (c >= '0' && c <= '9')
            value = c - '0';
        else if (c >= 'A' && c <= 'F')
            value = c - 'A' + 10;
        else if (c >= 'a' && c <= 'f')
            value = c - 'a' + 10;
        else
            return false; // invalid hex

        *addr = (*addr << 4) | value;
    }

    return true;
}


// parses the "&<hex>$" address of the current command. On a malformed address it reports
// "bad address" and returns false: the command must not run (address 0 is boot1)
bool decompose_addr(u32 *addr) {

    char *start = strchr(str,'&');
    char *end = strchr(str,'$');

    if(!(start && end) || end - start <= 1 || !addr_to_u32((u8*)start-str,(u8*)end-str,addr)) {
        puts("bad address");
        return false;
    }

   // printf("addr: %x\n",*addr);

    return true;
}


inline int read_byte_blocking(void) {
    uint8_t b;
    while (tud_cdc_read(&b, 1) != 1) {}
    return b;
}


#define BYTE_TIMEOUT_US 2000000 // a page transfer stalled for this long is abandoned

// returns the byte, or EOF if nothing arrives within BYTE_TIMEOUT_US
int read_byte_timeout(void) {
    uint8_t b;
    absolute_time_t end = make_timeout_time_us(BYTE_TIMEOUT_US);
    while (tud_cdc_read(&b, 1) != 1) {
        if (time_reached(end))
            return EOF;
    }
    return b;
}


// returns the number of bytes read: less than len if the host stopped sending
int read_n_bytes(u8 * buf, size_t idx, size_t len) {
    int i = 0;

    while(i < len) {

        int in = read_byte_timeout();

        if(in==EOF)
            break;

        buf[idx+i] = (u8)in;
        i++;
    }

    return i;
}


u8 test_val = 0; // for writing random to chip
u32 write_addr = 0;
bool readMode = false;
bool writeComplete = false;
char failMsg[20] = {0};

void console() {

    tud_task();

    str_idx =0;

    while(1){

        if(readMode){
            u8 chunk_idx = 0;
            writeComplete = false;


            // wait for chunk prefix
            u8 mrkr[4] = {0}; // 3 chars + terminator (copied into failMsg)
            if(read_n_bytes(mrkr,0,3) != 3){
                strcpy(failMsg ,"timeout");
                goto end;
            }

            if(strncmp(mrkr,BYTES_START,3)!=0){
                strcpy(failMsg ,mrkr);
                goto end;
            }

            while(chunk_idx != 8) {

            /*

                // get CRC32
                u32 crc = 0;
                read_n_bytes((u8*)(&crc),0,4);

                // get chunk
                buffer_bytes += read_n_bytes(pageBuffer,chunk_idx*CHUNK_SIZE,CHUNK_SIZE);

                if(crc != crc32(&pageBuffer[chunk_idx*CHUNK_SIZE],CHUNK_SIZE)){

                    strcpy(failMsg ,"bad crc!");

                    goto end;
                }*/

                int got = read_n_bytes(pageBuffer,chunk_idx*CHUNK_SIZE,CHUNK_SIZE);
                buffer_bytes += got;
                if(got != CHUNK_SIZE){
                    strcpy(failMsg ,"timeout");
                    goto end;
                }
                chunk_idx++;

            }

                // get chunk suffix
                if(read_n_bytes(mrkr,0,3) != 3){
                    strcpy(failMsg ,"timeout");
                    goto end;
                }
                if(strncmp(mrkr,BYTES_FINISHED,3)!=0){
                    strcpy(failMsg ,"bad $bf!");
                    goto end;
                }
    

            if(buffer_bytes!=PAGE_SIZE){

                strcpy(failMsg ,"bad buffer bytes!");

                goto end;
            }
            
            // send SHA
            get_buffer_SHA();

            // wait for SHA good
            char ack = '\0';
            read_n_bytes(&ack,0,1); // on timeout ack stays '\0': page not written

            if(ack != 'w'){
                // host rejected the buffer (e.g. bad SHA): drop the page, host will resend it
                strcpy(failMsg,"page not written");

                goto end;
            }

            
            write_page(write_addr,pageBuffer,PAGE_SIZE,false,0x0); // buffer write

            puts("wc\n"); // ack write complete
            
            writeComplete = true;

            end:

                readMode = false;
                str_idx = 0;
                buffer_bytes = 0;

                // report the failure and go back to the console: the host retries the page
                if(!writeComplete)
                    printf("%s\n",failMsg);

                writeComplete = false;
                continue;
        }




        int in = read_byte_blocking();


        if(in>0){
            // garbage without "$me" (e.g. the rest of an abandoned page): start over instead of
            // writing past the end of str
            if(str_idx >= sizeof(str) - 1)
                str_idx = 0;

            str[str_idx++]  = (u8)in;

            if(marker_found(MESSAGE_END)){
                str_idx-=LEN_MSG_END;
                str[str_idx] = '\0'; // strchr() in decompose_addr() must not see older commands

                u32 addr;



                 if(marker_found(PAGE_IN)) {
                    readMode = true;
                    buffer_bytes =0;
                    str_idx = 0;
                   // memset(pageBuffer,0,PAGE_SIZE);

                    continue;
                 }


                else if(marker_found(SET_W_ADDR)) {
                    if(decompose_addr(&addr))
                        write_addr = addr&0x3ffff;
                   // printf("page address set to 0x%x\n",write_addr);

                }
                

                else if(marker_found(CLR)){
                    str_idx = 0;
                    memset(str,0,sizeof(str));
                }
                
                
                else if(marker_found(SET_W_TST_VAL)){
                    if(decompose_addr(&addr)){
                        test_val = (u8)(addr&0xff); // test pattern set
                        printf("set test pattern to \"%x.\"\n",test_val);
                    }
                }

                else if(marker_found(TEST_W)){
                    if(decompose_addr(&addr))
                        write_page((addr&0x3ffff),NULL,PAGE_SIZE,true,test_val); // test pattern write
                }

                else if(marker_found(READ_PAGE)){
                    if(decompose_addr(&addr))
                        read_page((addr&0x3ffff));   // page read
                }

                else if(marker_found(BLOCK_SHA)){
                    if(decompose_addr(&addr))
                        get_block_SHA(addr&0xfff);
                }
                 else if(marker_found(PAGE_SHA)){
                    if(decompose_addr(&addr))
                        get_page_SHA(addr&0x3ffff);
                 }
                else if(marker_found(BLOCK_ERASE)){
                    if(decompose_addr(&addr)){
                        u32 block = addr&0xfff;
                        if(is_bad_block(block))
                            printf("block %d: bad block, skipped\n",block);
                        else
                            puts(erase_block(block) ? "erased" : "EERR"); // block erase (takes row address only)
                    }
                }
                else if(marker_found(CHIP_ERASE)){
                    erase_chip(); // full chip erase
                }
                else if(marker_found(NAND_ID)) {// id read
                    read_id();
                }
                
                str_idx = 0;
                str[0] = 0x0;
                //    memset(str,0,sizeof(str));

                }

            } 
            


        }

    }

    

int main()
{

    stdio_init_all();



    #ifdef PICO_W_BOARD

        // Initialise the Wi-Fi chip
        if (cyw43_arch_init()) {
            printf("Wi-Fi init failed\n");
            return -1;
        }
    #else
        gpio_init(LED_PIN);
        gpio_set_dir(LED_PIN,GPIO_OUT);
    #endif

    init_gpio();

    while (!stdio_usb_connected()) {
        sleep_ms(10);
    }
        sleep_ms(100);


    console();

}
